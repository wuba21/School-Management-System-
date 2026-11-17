import os
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.http import FileResponse, Http404, HttpResponseForbidden
from django.views.decorators.http import require_POST
from django.conf import settings
from django.utils import timezone
from django.db.models import Sum

from accounts.decorators import sysadmin_required
from backup.models import BackupRecord
from backup.services import BackupService, validate_safe_path
from backup.forms import BackupFilterForm, USBExportForm
from core.models import AuditLog


@sysadmin_required
def backup_dashboard_view(request):
    """
    Administrative Backup and Recovery Dashboard.
    Restricted strictly to System Administrators (ADMIN role).
    """
    filter_form = BackupFilterForm(request.GET)
    export_form = USBExportForm()

    records = BackupRecord.objects.all()

    if filter_form.is_valid():
        b_type = filter_form.cleaned_data.get('backup_type')
        status = filter_form.cleaned_data.get('status')
        search = filter_form.cleaned_data.get('search')

        if b_type:
            records = records.filter(backup_type=b_type)
        if status:
            records = records.filter(status=status)
        if search:
            records = records.filter(filename__icontains=search) | records.filter(notes__icontains=search)

    # Summary Statistics
    total_db_backups = BackupRecord.objects.filter(backup_type='DATABASE', status='COMPLETED').count()
    total_media_backups = BackupRecord.objects.filter(backup_type='MEDIA', status='COMPLETED').count()
    
    total_size_bytes = BackupRecord.objects.filter(status='COMPLETED').aggregate(total=Sum('file_size_bytes'))['total'] or 0
    
    # Calculate human readable total size
    human_total_size = "0 B"
    size_float = float(total_size_bytes)
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_float < 1024.0:
            human_total_size = f"{size_float:.2f} {unit}"
            break
        size_float /= 1024.0

    last_db_backup = BackupRecord.objects.filter(backup_type='DATABASE', status='COMPLETED').first()
    last_media_backup = BackupRecord.objects.filter(backup_type='MEDIA', status='COMPLETED').first()

    context = {
        'active_menu': 'backup',
        'page_title': 'Backup & Recovery Management',
        'records': records[:100],
        'filter_form': filter_form,
        'export_form': export_form,
        'total_db_backups': total_db_backups,
        'total_media_backups': total_media_backups,
        'total_size_human': human_total_size,
        'last_db_backup': last_db_backup,
        'last_media_backup': last_media_backup,
        'backup_root': str(getattr(settings, 'BACKUP_ROOT', settings.BASE_DIR / 'backups')),
        'retention_policy': {
            'daily': getattr(settings, 'BACKUP_RETENTION_DAILY', 7),
            'weekly': getattr(settings, 'BACKUP_RETENTION_WEEKLY', 4),
            'monthly': getattr(settings, 'BACKUP_RETENTION_MONTHLY', 12),
        }
    }
    return render(request, 'backup/dashboard.html', context)


@sysadmin_required
@require_POST
def create_database_backup_view(request):
    """Creates a new database backup from the web dashboard."""
    prune = request.POST.get('prune') == 'true'
    try:
        record = BackupService.create_database_backup(
            user=request.user,
            compress=True,
            prune=prune,
            notes=f"Created via Admin Dashboard by {request.user.username}"
        )
        messages.success(
            request,
            f"Database backup '{record.filename}' ({record.file_size_human}) created successfully."
        )
    except Exception as e:
        messages.error(request, f"Database backup failed: {str(e)}")

    return redirect('backup_dashboard')


@sysadmin_required
@require_POST
def create_media_backup_view(request):
    """Creates a new media backup from the web dashboard."""
    prune = request.POST.get('prune') == 'true'
    try:
        record = BackupService.create_media_backup(
            user=request.user,
            prune=prune,
            notes=f"Created via Admin Dashboard by {request.user.username}"
        )
        messages.success(
            request,
            f"Media archive '{record.filename}' ({record.file_size_human}) created successfully."
        )
    except Exception as e:
        messages.error(request, f"Media backup failed: {str(e)}")

    return redirect('backup_dashboard')


@sysadmin_required
def download_backup_view(request, backup_id):
    """
    Secure file streaming for backup archives.
    Restricted strictly to administrators with path traversal mitigation.
    """
    record = get_object_or_404(BackupRecord, id=backup_id)
    backup_root = getattr(settings, 'BACKUP_ROOT', settings.BASE_DIR / 'backups')

    # Security check: Ensure file path is strictly within BACKUP_ROOT
    if not validate_safe_path(record.filepath, backup_root):
        return HttpResponseForbidden("Access denied: Invalid backup archive path.")

    if not record.exists_on_disk:
        raise Http404(f"Archive file '{record.filename}' does not exist on server storage.")

    # Audit log the download event
    AuditLog.objects.create(
        actor=request.user,
        action='CREATE',
        entity_name='BackupDownload',
        record_id=str(record.id),
        changes_json={
            'filename': record.filename,
            'size_bytes': record.file_size_bytes,
            'ip_address': request.META.get('REMOTE_ADDR'),
        }
    )

    response = FileResponse(
        open(record.filepath, 'rb'),
        as_attachment=True,
        filename=record.filename
    )
    return response


@sysadmin_required
@require_POST
def verify_backup_view(request, backup_id):
    """Tests archive decompression and SHA-256 integrity on demand."""
    record = get_object_or_404(BackupRecord, id=backup_id)
    is_valid, msg = BackupService.verify_backup_integrity(record)

    if is_valid:
        messages.success(request, f"Integrity Verified for '{record.filename}': {msg}")
    else:
        messages.error(request, f"Integrity Failure for '{record.filename}': {msg}")

    return redirect('backup_dashboard')


@sysadmin_required
@require_POST
def export_backup_usb_view(request):
    """Handles exporting a backup file to an external USB drive."""
    form = USBExportForm(request.POST)
    if form.is_valid():
        backup_id = form.cleaned_data['backup_id']
        dest_path = form.cleaned_data['destination_path']
        record = get_object_or_404(BackupRecord, id=backup_id)

        try:
            dest_file, checksum = BackupService.export_backup_to_usb(
                backup_record=record,
                destination_dir=dest_path,
                user=request.user
            )
            messages.success(
                request,
                f"Backup '{record.filename}' successfully copied to USB at '{dest_file}'. SHA-256 integrity verified."
            )
        except Exception as e:
            messages.error(request, f"USB Export failed: {str(e)}")
    else:
        messages.error(request, "Invalid export submission. Please provide a valid folder path.")

    return redirect('backup_dashboard')


@sysadmin_required
@require_POST
def prune_backups_view(request):
    """Runs GFS retention policy cleanup."""
    try:
        res = BackupService.prune_backups()
        messages.success(
            request,
            f"Retention pruning complete. Kept: {res['kept_count']}, Pruned: {res['pruned_count']} archives."
        )
    except Exception as e:
        messages.error(request, f"Retention pruning error: {str(e)}")

    return redirect('backup_dashboard')
