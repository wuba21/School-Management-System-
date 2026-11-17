"""
URL configuration for the Students application in SSMS.
"""

from django.urls import path
from students import views

urlpatterns = [
    path('', views.student_list_view, name='students_list'),
    path('register/', views.student_register_view, name='student_register'),

    # Step 22: Student ID Card Management & QR Verification
    path('id-cards/', views.id_card_hub_view, name='id_card_hub'),
    path('id-cards/preview/<int:student_id>/', views.id_card_preview_view, name='id_card_preview'),
    path('id-cards/generate/<int:student_id>/', views.id_card_generate_view, name='id_card_generate'),
    path('id-cards/batch-generate/', views.id_card_batch_generate_view, name='id_card_batch_generate'),
    path('id-cards/pdf/<int:card_id>/', views.id_card_pdf_view, name='id_card_pdf'),
    path('id-cards/batch-pdf/', views.id_card_batch_pdf_view, name='id_card_batch_pdf'),
    path('id-cards/revoke/<int:card_id>/', views.id_card_revoke_view, name='id_card_revoke'),
    path('id-cards/reprint/<int:card_id>/', views.id_card_reprint_view, name='id_card_reprint'),
    path('id-cards/verify/<uuid:card_uuid>/', views.id_card_verify_view, name='id_card_verify'),

    # Step 23: Student Transfer & Leaving Certificate Management
    path('certificates/', views.certificate_hub_view, name='certificate_hub'),
    path('certificates/create/', views.certificate_create_view, name='certificate_create_general'),
    path('certificates/create/<int:student_id>/', views.certificate_create_view, name='certificate_create'),
    path('certificates/preview/<int:certificate_id>/', views.certificate_preview_view, name='certificate_preview'),
    path('certificates/<int:certificate_id>/submit/', views.certificate_submit_view, name='certificate_submit'),
    path('certificates/<int:certificate_id>/approve/', views.certificate_approve_view, name='certificate_approve'),
    path('certificates/<int:certificate_id>/reject/', views.certificate_reject_view, name='certificate_reject'),
    path('certificates/<int:certificate_id>/issue/', views.certificate_issue_view, name='certificate_issue'),
    path('certificates/<int:certificate_id>/revoke/', views.certificate_revoke_view, name='certificate_revoke'),
    path('certificates/<int:certificate_id>/pdf/', views.certificate_pdf_view, name='certificate_pdf'),
    path('certificates/verify/', views.certificate_verify_view, name='certificate_verify'),

    path('<int:student_id>/', views.student_detail_view, name='student_detail'),
    path('<int:student_id>/edit/', views.student_edit_view, name='student_edit'),
    path('<int:student_id>/enroll/', views.student_enroll_view, name='student_enroll'),
    path('<int:student_id>/status/', views.student_status_view, name='student_status'),
]
