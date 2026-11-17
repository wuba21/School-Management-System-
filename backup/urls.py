from django.urls import path
from backup import views

urlpatterns = [
    path('', views.backup_dashboard_view, name='backup_dashboard'),
    path('database/create/', views.create_database_backup_view, name='backup_database_create'),
    path('media/create/', views.create_media_backup_view, name='backup_media_create'),
    path('download/<int:backup_id>/', views.download_backup_view, name='backup_download'),
    path('verify/<int:backup_id>/', views.verify_backup_view, name='backup_verify'),
    path('export/usb/', views.export_backup_usb_view, name='backup_export_usb'),
    path('prune/', views.prune_backups_view, name='backup_prune'),
]
