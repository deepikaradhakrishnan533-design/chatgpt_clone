from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static

from chat import views


urlpatterns = [
    path(
        "admin/",
        admin.site.urls
    ),
    path(
    "image-search/",
    views.image_search,
    name="image_search",
),

    # Authentication
    path(
        "signup/",
        views.signup,
        name="signup"
    ),
    path(
        "login/",
        views.login_view,
        name="login"
    ),
    path(
        "logout/",
        views.logout_view,
        name="logout"
    ),

    # Chat
    path(
        "",
        views.chat_home,
        name="chat_home"
    ),
    path(
        "new-chat/",
        views.new_chat,
        name="new_chat"
    ),
    path(
        "chat/<int:conversation_id>/",
        views.open_chat,
        name="open_chat"
    ),
    path(
        "delete-chat/<int:conversation_id>/",
        views.delete_chat,
        name="delete_chat"
    ),
    path(
        "rename-chat/<int:conversation_id>/",
        views.rename_chat,
        name="rename_chat"
    ),

    # Document Library
    path(
        "library/",
        views.library,
        name="library"
    ),
    path(
        "delete-document/<int:document_id>/",
        views.delete_document,
        name="delete_document"
    ),

    # Projects
    path(
        "projects/",
        views.projects,
        name="projects"
    ),
    path(
        "delete-project/<int:project_id>/",
        views.delete_project,
        name="delete_project"
    ),
    path(
    "project/<int:project_id>/upload-document/",
    views.upload_project_document,
    name="upload_project_document"
),
]


if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT
    )