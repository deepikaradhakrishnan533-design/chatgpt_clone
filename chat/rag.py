"""Retrieval-augmented generation utilities for the chat application."""

from pathlib import Path
import re

import chromadb
from pypdf import PdfReader


# Base project directory
BASE_DIR = Path(__file__).resolve().parent.parent


# Chroma database
chroma_client = chromadb.PersistentClient(
    path=str(BASE_DIR / "chroma_db")
)


def get_collection():
    """Get the current ChromaDB collection."""
    return chroma_client.get_or_create_collection(
        name="documents"
    )


def get_embedding_model():
    """Load the embedding model only when it is needed."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer("all-MiniLM-L6-v2")


def split_into_sections(text):
    """
    Split a CV into sections, including headings that
    PDF extraction may accidentally join together.
    """

    headings = [
        "Objective",
        "Professional Summary",
        "Core Competencies",
        "Professional Experience",
        "Experience",
        "Education",
        "Skills",
        "Projects",
        "Area Of Specialization",
        "Languages",
        "Personal Details",
        "Reference",
        "Additional Information",
        "Certifications",
        "Declaration",
    ]

    # Fix common PDF ligatures.
    text = text.replace("\ufb01", "fi")
    text = text.replace("\ufb00", "ff")
    text = text.replace("\ufb02", "fl")
    text = text.replace("\ufb03", "ffi")
    text = text.replace("\ufb04", "ffl")

    # Add a newline before headings accidentally joined
    # to the previous text.
    for heading in headings:
        text = re.sub(
            rf"(?<!\n)({re.escape(heading)})",
            r"\n\1",
            text,
            flags=re.IGNORECASE,
        )

    sections = []
    current_section = ""

    for line in text.splitlines():
        line = line.strip()

        if not line:
            continue

        matched_heading = None

        for heading in headings:
            if line.lower() == heading.lower():
                matched_heading = heading
                break

        if matched_heading:
            if current_section:
                sections.append(
                    current_section.strip()
                )

            current_section = matched_heading

        else:
            current_section += "\n" + line

    if current_section:
        sections.append(
            current_section.strip()
        )

    return sections


def process_pdf(file_path, document_id, user_id):
    """
    Read a PDF, split it into sections, create embeddings,
    and store them in ChromaDB.
    """
    # pylint: disable=too-many-locals

    current_collection = get_collection()

    reader = PdfReader(file_path)

    text = ""

    for page in reader.pages:
        text += page.extract_text() or ""

    sections = split_into_sections(text)

    if not sections:
        return 0

    # Remove previously stored sections for this document.
    current_collection.delete(
        where={
            "document_id": str(document_id)
        }
    )

    # Load the model only when document processing is needed.
    embedding_model = get_embedding_model()

    embeddings = embedding_model.encode(
        sections
    ).tolist()

    ids = [
        f"{document_id}_{index}"
        for index in range(len(sections))
    ]

    current_collection.add(
        ids=ids,
        documents=sections,
        embeddings=embeddings,
        metadatas=[
            {
                "document_id": str(document_id),
                "user_id": str(user_id),
            }
            for _ in sections
        ],
    )

    return len(sections)


def search_documents(
    question,
    user_id,
    number_of_results=3,
):
    """
    Search the user's documents.

    If the question contains a known CV section keyword,
    return that section directly. Otherwise, use semantic search.
    """

    current_collection = get_collection()

    question_lower = question.lower()

    section_keywords = {
        "skills": "Skills",
        "skill": "Skills",
        "education": "Education",
        "study": "Education",
        "degree": "Education",
        "qualification": "Education",
        "experience": "Professional Experience",
        "professional experience": "Professional Experience",
        "work": "Professional Experience",
        "job": "Professional Experience",
        "project": "Projects",
        "projects": "Projects",
        "certification": "Certifications",
        "certifications": "Certifications",
        "specialization": "Area Of Specialization",
        "language": "Languages",
        "languages": "Languages",
    }

    target_section = None

    for keyword, section in section_keywords.items():
        if keyword in question_lower:
            target_section = section
            break

    # Get documents belonging to this user.
    user_documents = current_collection.get(
        where={
            "user_id": str(user_id)
        }
    )

    documents = user_documents["documents"]

    # If the question clearly asks about a particular
    # CV section, return that section directly.
    if target_section:
        matching_sections = []

        for document in documents:
            first_line = (
                document.split("\n")[0].strip()
            )

            if (
                first_line.lower()
                == target_section.lower()
            ):
                matching_sections.append(document)

        if matching_sections:
            return matching_sections[
                :number_of_results
            ]

    # If there are no documents, return an empty list.
    if not documents:
        return []

    # Load the model only for semantic search.
    embedding_model = get_embedding_model()

    query_embedding = embedding_model.encode(
        question
    ).tolist()

    results = current_collection.query(
        query_embeddings=[query_embedding],
        n_results=number_of_results,
        where={
            "user_id": str(user_id)
        },
    )

    return results["documents"][0]


def get_document_context(
    question,
    user_id,
    number_of_results=3,
):
    """Get relevant information from uploaded documents."""

    results = search_documents(
        question,
        user_id,
        number_of_results,
    )

    if not results:
        return (
            "No relevant information was found "
            "in the uploaded documents."
        )

    return "\n\n".join(results)