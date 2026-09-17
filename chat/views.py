"""Views for authentication, chat, documents, images, and projects."""

import base64
import io
import os
import re

import requests
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.forms import UserCreationForm
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from openai import OpenAI
from PIL import Image

from .models import Conversation
from .models import Document
from .models import Message
from .models import Project
from .rag import collection
from .rag import get_document_context
from .rag import process_pdf


client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)


def clean_ai_response(text):
    """Remove Markdown formatting from AI responses."""
    if not text:
        return ""

    replacements = [
        ("**", ""),
        ("###", ""),
        ("##", ""),
        ("```python", ""),
        ("```", ""),
    ]

    for old_text, new_text in replacements:
        text = text.replace(old_text, new_text)

    text = re.sub(
        r"\n{3,}",
        "\n\n",
        text
    )

    return text.strip()


def create_image_input(uploaded_image, question):
    """Convert an uploaded image to JPEG for OpenAI."""
    image_bytes = uploaded_image.read()

    image = Image.open(
        io.BytesIO(image_bytes)
    )

    image = image.convert("RGB")

    output = io.BytesIO()

    image.save(
        output,
        format="JPEG",
        quality=90
    )

    jpeg_bytes = output.getvalue()

    encoded_image = base64.b64encode(
        jpeg_bytes
    ).decode("utf-8")

    return [
        {
            "type": "input_text",
            "text": question,
        },
        {
            "type": "input_image",
            "image_url": (
                f"data:image/jpeg;base64,{encoded_image}"
            ),
        },
    ]


def get_ai_instructions(message, user):
    """Create instructions for normal or document-based questions."""
    has_documents = Document.objects.filter(
        user=user
    ).exists()

    if has_documents:
        document_context = get_document_context(
            message,
            user.id,
            3
        )

        return f"""
You are a helpful AI assistant.

The user has uploaded documents.

Use the following document context when it
is relevant to the user's question.

DOCUMENT CONTEXT:
{document_context}

Important response rules:

- Answer using the document context when the
  question is about the uploaded documents.
- Use plain text only.
- Do not use Markdown.
- Do not use bold formatting.
- Do not use italic formatting.
- Do not use asterisks.
- Do not use double asterisks.
- Do not use Markdown headings.
- Use simple plain-text bullet points when useful.
- Do not invent information.
- If the document does not contain the answer,
  clearly say that the information was not found
  in the uploaded document.
- For normal questions unrelated to the documents,
  answer normally.
"""

    return """
You are a helpful AI assistant.

Response rules:

- Use plain text only.
- Do not use Markdown.
- Do not use bold formatting.
- Do not use italic formatting.
- Do not use asterisks.
- Do not use double asterisks.
- Do not use Markdown headings.
- Use simple plain-text bullet points when useful.

Answer the user's questions clearly and naturally.
"""


def get_chat_history(conversation):
    """Build conversation history for the AI."""
    history = []

    for msg in conversation.messages.all():
        history.append(
            {
                "role": (
                    "user"
                    if msg.sender == "user"
                    else "assistant"
                ),
                "content": msg.content,
            }
        )

    return history


def generate_ai_response(
    conversation,
    question,
    user,
    uploaded_image=None
):
    """Generate an AI response for text or image questions."""
    history = get_chat_history(conversation)

    instructions = get_ai_instructions(
        question,
        user
    )

    if uploaded_image:
        image_content = create_image_input(
            uploaded_image,
            question
        )

        if history:
            history[-1]["content"] = image_content
        else:
            history.append(
                {
                    "role": "user",
                    "content": image_content,
                }
            )

    response = client.responses.create(
        model="gpt-5.6-luna",
        instructions=instructions,
        input=history
    )

    return clean_ai_response(
        response.output_text
    )


def render_chat_error(
    request,
    conversation,
    error_message
):
    """Render chat page with an error message."""
    conversations = Conversation.objects.filter(
        user=request.user
    )

    messages = conversation.messages.all()

    return render(
        request,
        "chat/chat_home.html",
        {
            "conversation": conversation,
            "messages": messages,
            "conversations": conversations,
            "image_error": error_message,
        }
    )


def handle_message(
    request,
    conversation
):
    """Process a text or image message."""
    message = request.POST.get(
        "message",
        ""
    ).strip()

    uploaded_image = request.FILES.get(
        "image"
    )

    if not message and not uploaded_image:
        return None

    if uploaded_image:
        content_type = (
            uploaded_image.content_type or ""
        )

        if not content_type.startswith("image/"):
            return "ERROR_IMAGE"

        if uploaded_image.size > 10 * 1024 * 1024:
            return "ERROR_SIZE"

    question = message

    if not question:
        question = (
            "Please describe and analyze this image."
        )

    Message.objects.create(
        conversation=conversation,
        sender="user",
        content=question
    )

    if conversation.title == "New Chat":
        conversation.title = question[:30]
        conversation.save()

    assistant_reply = generate_ai_response(
        conversation,
        question,
        request.user,
        uploaded_image
    )

    Message.objects.create(
        conversation=conversation,
        sender="assistant",
        content=assistant_reply
    )

    return "SUCCESS"


# =========================================================
# NEW: IMAGE SEARCH
# =========================================================

@login_required
def image_search(request):
    """Search Pexels for reference images."""
    query = request.GET.get(
        "q",
        ""
    ).strip()

    if not query:
        return JsonResponse(
            {
                "error": (
                    "Please provide an image "
                    "search query."
                )
            },
            status=400
        )

    api_key = os.getenv(
        "PEXELS_API_KEY"
    )

    if not api_key:
        return JsonResponse(
            {
                "error": (
                    "PEXELS_API_KEY is not configured."
                )
            },
            status=500
        )

    try:
        response = requests.get(
            "https://api.pexels.com/v1/search",
            headers={
                "Authorization": api_key
            },
            params={
                "query": query,
                "per_page": 6,
                "locale": "en-US"
            },
            timeout=15
        )

    except requests.RequestException:
        return JsonResponse(
            {
                "error": (
                    "Unable to connect to "
                    "the image search service."
                )
            },
            status=503
        )

    if response.status_code != 200:
        return JsonResponse(
            {
                "error": "Image search failed."
            },
            status=response.status_code
        )

    data = response.json()

    images = []

    for photo in data.get(
        "photos",
        []
    ):

        images.append(
            {
                "id": photo.get("id"),
                "image": photo.get(
                    "src",
                    {}
                ).get(
                    "medium"
                ),
                "small": photo.get(
                    "src",
                    {}
                ).get(
                    "small"
                ),
                "page": photo.get(
                    "url"
                ),
                "photographer": photo.get(
                    "photographer"
                ),
                "photographer_url": photo.get(
                    "photographer_url"
                ),
                "alt": (
                    photo.get("alt")
                    or query
                ),
            }
        )

    return JsonResponse(
        {
            "query": query,
            "images": images
        }
    )


# =========================================================
# AUTHENTICATION
# =========================================================

def signup(request):
    """Create a new user account."""
    if request.method == "POST":
        form = UserCreationForm(request.POST)

        if form.is_valid():
            user = form.save()
            login(request, user)

            return redirect("chat_home")

    else:
        form = UserCreationForm()

    return render(
        request,
        "chat/signup.html",
        {"form": form}
    )


def login_view(request):
    """Log an existing user into the application."""
    if request.method == "POST":
        form = AuthenticationForm(
            request,
            data=request.POST
        )

        if form.is_valid():
            user = form.get_user()
            login(request, user)

            return redirect("chat_home")

    else:
        form = AuthenticationForm()

    return render(
        request,
        "chat/login.html",
        {"form": form}
    )


# =========================================================
# CHAT HOME
# =========================================================

@login_required
def chat_home(request):
    """Display the user's main chat page."""
    conversation = Conversation.objects.filter(
        user=request.user
    ).first()

    if not conversation:
        conversation = Conversation.objects.create(
            user=request.user,
            title="New Chat"
        )

    if request.method == "POST":

        if request.FILES.get("document"):
            uploaded_file = request.FILES["document"]

            document = Document.objects.create(
                user=request.user,
                file=uploaded_file
            )

            process_pdf(
                document.file.path,
                document.id,
                request.user.id
            )

            return redirect(
                "open_chat",
                conversation_id=conversation.id
            )

        result = handle_message(
            request,
            conversation
        )

        if result == "ERROR_IMAGE":
            return render_chat_error(
                request,
                conversation,
                "Please select a valid image file."
            )

        if result == "ERROR_SIZE":
            return render_chat_error(
                request,
                conversation,
                "Image size must be 10 MB or less."
            )

        if result == "SUCCESS":
            return redirect(
                "open_chat",
                conversation_id=conversation.id
            )

    conversations = Conversation.objects.filter(
        user=request.user
    )

    messages = conversation.messages.all()

    return render(
        request,
        "chat/chat_home.html",
        {
            "conversation": conversation,
            "messages": messages,
            "conversations": conversations
        }
    )


# =========================================================
# NEW CHAT
# =========================================================

@login_required
def new_chat(request):
    """Create a new conversation."""
    project_id = request.GET.get("project")

    project = None

    if project_id:
        project = Project.objects.filter(
            id=project_id,
            user=request.user
        ).first()

    conversation = Conversation.objects.create(
        user=request.user,
        project=project,
        title="New Chat"
    )

    return redirect(
        "open_chat",
        conversation_id=conversation.id
    )


# =========================================================
# OPEN CHAT
# =========================================================

@login_required
def open_chat(request, conversation_id):
    """Open and process a specific conversation."""
    conversation = get_object_or_404(
        Conversation,
        id=conversation_id,
        user=request.user
    )

    if request.method == "POST":

        if request.FILES.get("document"):
            uploaded_file = request.FILES["document"]

            document = Document.objects.create(
                user=request.user,
                file=uploaded_file
            )

            process_pdf(
                document.file.path,
                document.id,
                request.user.id
            )

            return redirect(
                "open_chat",
                conversation_id=conversation.id
            )

        result = handle_message(
            request,
            conversation
        )

        if result == "ERROR_IMAGE":
            return render_chat_error(
                request,
                conversation,
                "Please select a valid image file."
            )

        if result == "ERROR_SIZE":
            return render_chat_error(
                request,
                conversation,
                "Image size must be 10 MB or less."
            )

        if result == "SUCCESS":
            return redirect(
                "open_chat",
                conversation_id=conversation.id
            )

    conversations = Conversation.objects.filter(
        user=request.user
    )

    messages = conversation.messages.all()

    return render(
        request,
        "chat/chat_home.html",
        {
            "conversation": conversation,
            "messages": messages,
            "conversations": conversations
        }
    )


# =========================================================
# DELETE CHAT
# =========================================================

@login_required
def delete_chat(request, conversation_id):
    """Delete a conversation."""
    conversation = get_object_or_404(
        Conversation,
        id=conversation_id,
        user=request.user
    )

    conversation.delete()

    return redirect("chat_home")


# =========================================================
# RENAME CHAT
# =========================================================

@login_required
def rename_chat(request, conversation_id):
    """Rename a conversation."""
    conversation = get_object_or_404(
        Conversation,
        id=conversation_id,
        user=request.user
    )

    if request.method == "POST":

        new_title = request.POST.get(
            "title"
        )

        if new_title:
            conversation.title = new_title
            conversation.save()

    return redirect(
        "open_chat",
        conversation_id=conversation.id
    )


# =========================================================
# LOGOUT
# =========================================================

def logout_view(request):
    """Log the user out."""
    logout(request)

    return redirect("login")


# =========================================================
# LIBRARY
# =========================================================

@login_required
def library(request):
    """Display and upload documents."""
    if request.method == "POST":

        uploaded_file = request.FILES.get(
            "document"
        )

        if uploaded_file:
            document = Document.objects.create(
                user=request.user,
                file=uploaded_file
            )

            process_pdf(
                document.file.path,
                document.id,
                request.user.id
            )

            return redirect("library")

    documents = Document.objects.filter(
        user=request.user
    ).order_by("-uploaded_at")

    return render(
        request,
        "chat/library.html",
        {"documents": documents}
    )


# =========================================================
# DELETE DOCUMENT
# =========================================================

@login_required
def delete_document(request, document_id):
    """Delete a document and its vector data."""
    document = get_object_or_404(
        Document,
        id=document_id,
        user=request.user
    )

    document_path = document.file.path

    collection.delete(
        where={
            "document_id": str(document.id)
        }
    )

    document.delete()

    if os.path.exists(document_path):
        os.remove(document_path)

    return redirect("library")


# =========================================================
# PROJECTS
# =========================================================

@login_required
def projects(request):
    """Display the user's projects and their chats."""
    projects_list = Project.objects.filter(
        user=request.user
    ).prefetch_related(
        "conversations"
    ).order_by(
        "-created_at"
    )

    if request.method == "POST":

        project_name = request.POST.get(
            "name"
        )

        if project_name:
            Project.objects.create(
                user=request.user,
                name=project_name
            )

        return redirect("projects")

    return render(
        request,
        "chat/projects.html",
        {
            "projects": projects_list
        }
    )


# =========================================================
# DELETE PROJECT
# =========================================================

@login_required
def delete_project(request, project_id):
    """Delete a project."""
    project = get_object_or_404(
        Project,
        id=project_id,
        user=request.user
    )

    project.delete()

    return redirect("projects")


# =========================================================
# PROJECT DOCUMENT UPLOAD
# =========================================================

@login_required
def upload_project_document(
    request,
    project_id
):
    """Upload a document to a specific project."""
    project = get_object_or_404(
        Project,
        id=project_id,
        user=request.user
    )

    if request.method == "POST":

        uploaded_file = request.FILES.get(
            "document"
        )

        if uploaded_file:

            document = Document.objects.create(
                user=request.user,
                project=project,
                file=uploaded_file
            )

            process_pdf(
                document.file.path,
                document.id,
                request.user.id
            )

    return redirect("projects")