"""Database models for the chat application."""

from django.contrib.auth.models import User
from django.db import models


class Project(models.Model):
    """Store a user's project."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )
    name = models.CharField(
        max_length=200
    )
    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        """Return the project name."""
        return str(self.name)


class Conversation(models.Model):
    """Store a chat conversation."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conversations"
    )
    title = models.CharField(
        max_length=200,
        default="New Chat"
    )
    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        """Return the conversation title."""
        return str(self.title)


class Message(models.Model):
    """Store a message in a conversation."""

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages"
    )
    sender = models.CharField(
        max_length=10
    )
    content = models.TextField()
    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        """Return a short representation of the message."""
        return f"{self.sender}: {self.content[:30]}"  # pylint: disable=unsubscriptable-object


class Document(models.Model):
    """Store a document uploaded by a user."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE
    )
    project = models.ForeignKey(
        Project,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="documents"
    )
    file = models.FileField(
        upload_to="documents/"
    )
    uploaded_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        """Return the document file name."""
        return str(self.file.name)
