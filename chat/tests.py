from django.test import TestCase
from django.contrib.auth.models import User

from .models import Conversation, Message, Document


class ModelTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser",
            password="TestPass123"
        )

    def test_conversation_creation(self):
        conversation = Conversation.objects.create(
            user=self.user,
            title="Test Chat"
        )

        self.assertEqual(conversation.title, "Test Chat")
        self.assertEqual(conversation.user, self.user)

    def test_message_creation(self):
        conversation = Conversation.objects.create(
            user=self.user,
            title="Test Chat"
        )

        message = Message.objects.create(
            conversation=conversation,
            sender="user",
            content="Hello"
        )

        self.assertEqual(message.sender, "user")
        self.assertEqual(message.content, "Hello")
        self.assertEqual(
            message.conversation,
            conversation
        )

    def test_document_creation(self):
        document = Document.objects.create(
            user=self.user,
            file="documents/test.pdf"
        )

        self.assertEqual(document.user, self.user)
        self.assertEqual(
            document.file.name,
            "documents/test.pdf"
        )