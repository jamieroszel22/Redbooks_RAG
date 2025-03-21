#!/usr/bin/env python3
"""
DocRAG - Simple PDF Processor
A straightforward PDF processing script for generating text, JSON, and markdown from documents
"""
import os
import sys
import json
import uuid
import argparse
from pathlib import Path
from datetime import datetime

def get_file_info(file_path):
    """Get detailed information about a file"""
    stats = file_path.stat()
    size_mb = stats.st_size / (1024 * 1024)  # Convert to MB
    mod_time = datetime.fromtimestamp(stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
    return {
        'size_mb': round(size_mb, 2),
        'modified': mod_time
    }

def get_processed_info(name, chunks_dir, docs_dir, ollama_dir):
    """Get information about processed files"""
    info = {}

    # Check chunks file
    chunks_file = chunks_dir / f"{name}_chunks.json"
    if chunks_file.exists():
        with open(chunks_file, 'r', encoding="utf-8") as f:
            chunks = json.load(f)
            info['chunks_count'] = len(chunks)

    # Check individual document directory
    doc_dir = docs_dir / name
    if doc_dir.exists():
        # Check text file
        text_file = doc_dir / f"{name}.txt"
        if text_file.exists():
            info['text_size_mb'] = round(text_file.stat().st_size / (1024 * 1024), 2)
            with open(text_file, 'r', encoding="utf-8") as f:
                info['text_lines'] = sum(1 for _ in f)

        # Check JSON file
        json_file = doc_dir / f"{name}.json"
        if json_file.exists():
            info['json_size_mb'] = round(json_file.stat().st_size / (1024 * 1024), 2)

        # Check Markdown file
        md_file = doc_dir / f"{name}.md"
        if md_file.exists():
            info['md_size_mb'] = round(md_file.stat().st_size / (1024 * 1024), 2)
    else:
        # Check old text file structure for backward compatibility
        text_file = docs_dir / f"{name}.txt"
        if text_file.exists():
            info['text_size_mb'] = round(text_file.stat().st_size / (1024 * 1024), 2)
            with open(text_file, 'r', encoding="utf-8") as f:
                info['text_lines'] = sum(1 for _ in f)

    # Check Ollama file
    ollama_file = ollama_dir / f"{name}_ollama.jsonl"
    if ollama_file.exists():
        info['ollama_size_mb'] = round(ollama_file.stat().st_size / (1024 * 1024), 2)

    return info

def is_pdf_processed(pdf_name, chunks_dir):
    """Check if a PDF has already been processed"""
    chunk_file = chunks_dir / f"{pdf_name}_chunks.json"
    return chunk_file.exists()

def prepare_openwebui_collection(chunks_dir, output_dir, collection_name="Document Knowledge Base"):
    """Prepare chunks for Open WebUI collection"""
    print("\nPreparing Open WebUI collection...")

    # Create OpenWebUI directory
    openwebui_dir = output_dir / "openwebui"
    openwebui_dir.mkdir(parents=True, exist_ok=True)
    output_file = openwebui_dir / "knowledge_collection.json"

    # Load all chunks
    all_chunks = []
    chunk_files = list(chunks_dir.glob("*_chunks.json"))

    for chunk_file in chunk_files:
        try:
            with open(chunk_file, "r", encoding="utf-8") as f:
                chunks = json.load(f)
                all_chunks.extend(chunks)
                print(f"Loaded {len(chunks)} chunks from {chunk_file.name}")
        except Exception as e:
            print(f"Error loading {chunk_file}: {str(e)}")

    if not all_chunks:
        print("No chunks found for Open WebUI collection")
        return

    print(f"Loaded {len(all_chunks)} total chunks")

    # Group chunks by document source
    docs_by_source = {}
    for chunk in all_chunks:
        source = chunk["metadata"]["source"]
        if source not in docs_by_source:
            docs_by_source[source] = []
        docs_by_source[source].append(chunk)

    # Create Open WebUI collection structure
    collection = {
        "name": collection_name,
        "documents": []
    }

    # Process each document
    for source, doc_chunks in docs_by_source.items():
        doc_id = str(uuid.uuid4())
        document = {
            "id": doc_id,
            "url": "",
            "title": source,
            "content_chunks": []
        }

        # Add chunks for this document
        for i, chunk in enumerate(doc_chunks):
            chunk_id = str(uuid.uuid4())
            document["content_chunks"].append({
                "id": chunk_id,
                "doc_id": doc_id,
                "content": chunk["text"],
                "metadata": {
                    "source": source,
                    "chunk_index": i,
                    "total_chunks": len(doc_chunks)
                }
            })

        collection["documents"].append(document)

    # Save to file
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(collection, f, ensure_ascii=False, indent=2)

    print(f"Created Open WebUI collection with {len(collection['documents'])} documents")
    print(f"Saved to {output_file}")

    # Create and save import instructions
    instructions = f"""
Open WebUI Collection Created: {collection_name}

To import this collection into Open WebUI:

1. Open the Open WebUI interface
2. Go to Collections
3. Click "Import Collection"
4. Select the file: {output_file}
5. Verify the import was successful

You can now use this collection in your RAG workflows in Open WebUI.
"""

    instructions_file = output_file.parent / f"{output_file.stem}_import_instructions.txt"
    with open(instructions_file, "w", encoding="utf-8") as f:
        f.write(instructions)

    print(f"Import instructions saved to {instructions_file}")

def generate_markdown(text, title, page_count, pdf_filename, processed_date):
    """Generate a nicely formatted markdown version of the document"""
    # Create a header with metadata
    markdown = f"""# {title}

**Source**: {pdf_filename}
**Pages**: {page_count}
**Processed**: {processed_date}

---

"""

    # Process the text to create a more readable markdown version
    # Split text into paragraphs
    paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]

    # Heuristic to identify potential headings
    for paragraph in paragraphs:
        # Check if paragraph looks like a heading (short, ends with colon, all caps, etc.)
        lines = paragraph.split('\n')
        if len(lines) == 1 and len(paragraph) < 100:
            if paragraph.isupper() or paragraph.endswith(':') or paragraph.endswith('.'):
                # Likely a heading
                if len(paragraph) < 50:  # Short heading
                    markdown += f"## {paragraph}\n\n"
                else:  # Longer heading/subheading
                    markdown += f"### {paragraph}\n\n"
            else:
                # Regular paragraph
                markdown += f"{paragraph}\n\n"
        else:
            # Multi-line paragraph, check if it's a list
            if any(line.strip().startswith(('•', '-', '*', '1.', '2.')) for line in lines):
                # Format as a list
                for line in lines:
                    markdown += f"{line}\n"
                markdown += "\n"
            else:
                # Regular multi-line paragraph
                markdown += f"{' '.join(lines)}\n\n"

    return markdown

def process_pdfs(force_reprocess=False, skip_openwebui=False):
    """Process PDFs using a very simple approach"""
    # Install PyPDF2 if needed
    try:
        import PyPDF2
    except ImportError:
        print("Installing PyPDF2...")
        os.system(f"{sys.executable} -m pip install PyPDF2")
        import PyPDF2

    # Use relative paths for portability
    script_dir = Path(__file__).parent.absolute()
    pdfs_dir = script_dir / 'pdfs'
    output_dir = script_dir / 'processed_docs'
    docs_dir = output_dir / "docs"
    chunks_dir = output_dir / "chunks"
    ollama_dir = output_dir / "ollama"

    # Create directories
    for d in [docs_dir, chunks_dir, ollama_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # Get PDF files
    pdf_files = list(pdfs_dir.glob("*.pdf"))
    print(f"Found {len(pdf_files)} PDF files")

    processed_count = 0
    skipped_count = 0
    file_details = []

    # Process each PDF
    for pdf_file in pdf_files:
        file_info = {'name': pdf_file.name, **get_file_info(pdf_file)}
        name = pdf_file.stem

        # Create individual document directory
        doc_dir = docs_dir / name

        if not force_reprocess and is_pdf_processed(name, chunks_dir):
            print(f"Skipping {pdf_file.name} - already processed")
            file_info['status'] = 'skipped'
            file_info.update(get_processed_info(name, chunks_dir, docs_dir, ollama_dir))
            skipped_count += 1
        else:
            try:
                print(f"Processing {pdf_file.name}")

                # Extract text
                reader = PyPDF2.PdfReader(str(pdf_file))
                file_info['pages'] = len(reader.pages)

                text = ""
                for page in reader.pages:
                    text += page.extract_text() + "\n\n"

                # Create document directory if it doesn't exist
                doc_dir.mkdir(parents=True, exist_ok=True)

                # Save full text in document folder
                with open(doc_dir / f"{name}.txt", "w", encoding="utf-8") as f:
                    f.write(text)

                # Generate and save markdown version
                processed_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                markdown_content = generate_markdown(
                    text,
                    name,
                    len(reader.pages),
                    pdf_file.name,
                    processed_date
                )
                with open(doc_dir / f"{name}.md", "w", encoding="utf-8") as f:
                    f.write(markdown_content)

                # Create basic chunks (500 chars each with 50 char overlap)
                chunks = []
                chunk_size = 1000
                overlap = 100

                # Simple chunking by characters with overlap
                for i in range(0, len(text), chunk_size - overlap):
                    chunk = text[i:i + chunk_size]
                    if chunk:  # Only add non-empty chunks
                        chunks.append({
                            "text": chunk,
                            "metadata": {
                                "source": pdf_file.name,
                                "chunk_index": len(chunks),
                                "total_chunks": (len(text) // (chunk_size - overlap)) + 1
                            }
                        })

                # Save chunks
                with open(chunks_dir / f"{name}_chunks.json", "w", encoding="utf-8") as f:
                    json.dump(chunks, f, indent=2)

                # Save JSON in document folder
                with open(doc_dir / f"{name}.json", "w", encoding="utf-8") as f:
                    json.dump({
                        "title": name,
                        "source": pdf_file.name,
                        "pages": len(reader.pages),
                        "processed_date": processed_date,
                        "chunks_count": len(chunks),
                        "full_text": text
                    }, f, indent=2)

                # Save for Ollama
                with open(ollama_dir / f"{name}_ollama.jsonl", "w", encoding="utf-8") as f:
                    for chunk in chunks:
                        f.write(json.dumps(chunk) + "\n")

                print(f"Successfully processed {pdf_file.name}")
                print(f"Files saved in folder: {doc_dir}")
                file_info['status'] = 'processed'
                file_info.update(get_processed_info(name, chunks_dir, docs_dir, ollama_dir))
                processed_count += 1

            except Exception as e:
                print(f"Error with {pdf_file.name}: {e}")
                file_info['status'] = 'error'
                file_info['error'] = str(e)

        file_details.append(file_info)

    # Print detailed summary
    print("\nDetailed Processing Summary:")
    print("-" * 80)
    print(f"Total PDFs found: {len(pdf_files)}")
    print(f"Newly processed: {processed_count}")
    print(f"Skipped (already processed): {skipped_count}")
    print("\nFile Details:")
    print("-" * 80)

    for file_info in file_details:
        print(f"\nFile: {file_info['name']}")
        print(f"Status: {file_info['status']}")
        print(f"Size: {file_info['size_mb']} MB")
        print(f"Last modified: {file_info['modified']}")

        if 'pages' in file_info:
            print(f"Pages: {file_info['pages']}")
        if 'chunks_count' in file_info:
            print(f"Chunks generated: {file_info['chunks_count']}")
        if 'text_size_mb' in file_info:
            print(f"Extracted text size: {file_info['text_size_mb']} MB")
        if 'json_size_mb' in file_info:
            print(f"JSON file size: {file_info['json_size_mb']} MB")
        if 'md_size_mb' in file_info:
            print(f"Markdown file size: {file_info['md_size_mb']} MB")
        if 'text_lines' in file_info:
            print(f"Text lines: {file_info['text_lines']}")
        if 'ollama_size_mb' in file_info:
            print(f"Ollama file size: {file_info['ollama_size_mb']} MB")
        if 'error' in file_info:
            print(f"Error: {file_info['error']}")

    # Prepare Open WebUI collection if needed
    if not skip_openwebui and (processed_count > 0 or force_reprocess):
        prepare_openwebui_collection(chunks_dir, output_dir)

    return processed_count > 0 or skipped_count > 0

def main():
    parser = argparse.ArgumentParser(description='Process PDF files for RAG system')
    parser.add_argument('--force', action='store_true', help='Force reprocessing of all PDFs')
    parser.add_argument('--skip-openwebui', action='store_true', help='Skip Open WebUI collection preparation')
    args = parser.parse_args()

    if process_pdfs(force_reprocess=args.force, skip_openwebui=args.skip_openwebui):
        print("\nProcessing completed successfully!")
        print("\nYou can now run:")
        print("1. Simple query: ./run_simple_query.sh")
        print("2. Ollama RAG: ./run_rag_interactive.sh")
        sys.exit(0)
    else:
        print("\nNo files were processed successfully!")
        sys.exit(1)

if __name__ == "__main__":
    main()
