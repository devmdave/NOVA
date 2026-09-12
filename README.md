# NOVA

NOVA is a local-first AI image generation application where users can enter prompts and generate images on their own computer without sending their data to a cloud AI service.

## Architecture

This project is structured with a clean separation of concerns:
- **UI Layer (`app/ui/`)**: PySide6-based frontend.
- **Core Layer (`app/core/`)**: Foundational services, DI container, and logging.
- **Inference Layer (`app/inference/`)**: Abstractions for local AI image generation.
- **Model Management (`app/models/`)**: Handling downloading and managing AI models.
- **Config Layer (`app/config/`)**: Configuration and user settings management.

## Setup and Installation

Requires Python 3.9+

1. Create a virtual environment:
   ```bash
   python -m venv venv
   ```
2. Activate the virtual environment:
   - Windows: `.\venv\Scripts\activate`
   - Linux/Mac: `source venv/bin/activate`
3. Install dependencies:
   ```bash
   pip install -e .[dev]
   ```

## Running the Application

Once dependencies are installed, you can start the application by running:
```bash
python main.py
```

## Running Tests

To run the automated tests, ensure you have the `dev` dependencies installed and run:
```bash
pytest
```
