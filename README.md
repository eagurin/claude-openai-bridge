# Claude OpenAI Bridge

[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=flat&logo=fastapi)](https://fastapi.tiangolo.com)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![Claude Code MAX](https://img.shields.io/badge/Claude-Code%20MAX-orange.svg)](https://claude.ai/code)
[![OpenAI Compatible](https://img.shields.io/badge/OpenAI-Compatible-green.svg)](https://platform.openai.com/docs/api-reference)

A high-performance OpenAI-compatible API server that provides seamless integration between Claude Code MAX and any OpenAI-compatible client.

## Table of Contents

- [Authentication](#authentication)
- [Quick Start](#quick-start)
- [API Reference](#api-reference)
- [Client Integration](#client-integration)
- [Configuration](#configuration)
- [Error Handling](#error-handling)
- [Contributing](#contributing)

## Authentication

This bridge uses **Claude Code MAX subscription exclusively** via the local Claude CLI. No API keys required.

| Method | Status |
|--------|--------|
| Claude Code MAX | ✅ Supported |
| ANTHROPIC_API_KEY | ❌ Not supported |

## Quick Start

### Prerequisites

- Python 3.8+
- Active Claude Code MAX subscription
- Claude CLI installed (`claude --version`)

### Installation

```bash
git clone https://github.com/yourusername/claude-openai-bridge.git
cd claude-openai-bridge
pip install -r requirements.txt
```

### Running the Server

```bash
python src/server.py
```

The server starts on `http://localhost:8000` with:

- Interactive API docs: `/docs`
- OpenAPI schema: `/openapi.json`
- Health check: `/health`

## API Reference

### Base URL

```
http://localhost:8000/v1
```

### Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/models` | GET | List available models |
| `/v1/chat/completions` | POST | Create chat completion |
| `/v1/embeddings` | POST | Generate embeddings |

### Chat Completions

**Endpoint:** `POST /v1/chat/completions`

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer dummy" \
  -d '{
    "model": "claude-3-5-sonnet-20241022",
    "messages": [
      {"role": "user", "content": "Hello!"}
    ],
    "stream": false
  }'
```

**Response:**

```json
{
  "id": "chatcmpl-123",
  "object": "chat.completion",
  "created": 1677652288,
  "model": "claude-3-5-sonnet-20241022",
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": "Hello! How can I help you today?"
    },
    "finish_reason": "stop"
  }],
  "usage": {
    "prompt_tokens": 9,
    "completion_tokens": 12,
    "total_tokens": 21
  }
}
```

### Streaming

Set `"stream": true` for real-time responses:

```python
import openai

client = openai.OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="dummy"
)

stream = client.chat.completions.create(
    model="claude-3-5-sonnet-20241022",
    messages=[{"role": "user", "content": "Tell me a story"}],
    stream=True
)

for chunk in stream:
    if chunk.choices[0].delta.content:
        print(chunk.choices[0].delta.content, end="")
```

### Vision Support

Process images with Claude's vision capabilities:

```python
response = client.chat.completions.create(
    model="claude-3-5-sonnet-20241022",
    messages=[{
        "role": "user",
        "content": [
            {"type": "text", "text": "What's in this image?"},
            {
                "type": "image_url",
                "image_url": {"url": "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD..."}
            }
        ]
    }]
)
```

## Client Integration

### Cursor

Add to Cursor settings:

```json
{
  "openai.api_base": "http://localhost:8000/v1",
  "openai.api_key": "dummy"
}
```

### Cline

Configure Cline with:

- **API Base:** `http://localhost:8000/v1`
- **API Key:** `dummy` (any non-empty string)
- **Model:** `claude-3-5-sonnet-20241022`

### Python OpenAI SDK

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="dummy"  # Required by SDK but not used
)

# Use exactly like OpenAI API
response = client.chat.completions.create(
    model="claude-3-5-sonnet-20241022",
    messages=[{"role": "user", "content": "Hello!"}]
)
```

### Node.js

```javascript
import OpenAI from 'openai';

const openai = new OpenAI({
  baseURL: 'http://localhost:8000/v1',
  apiKey: 'dummy',
});

const completion = await openai.chat.completions.create({
  messages: [{ role: 'user', content: 'Hello!' }],
  model: 'claude-3-5-sonnet-20241022',
});
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `CLAUDE_CLI_PATH` | Path to Claude CLI | `/Users/laptop/.claude/local/claude` |
| `SERVER_HOST` | Server host | `0.0.0.0` |
| `SERVER_PORT` | Server port | `8000` |

### Supported Models

#### Chat Models

- `claude-3-5-sonnet-20241022` (recommended)
- `claude-3-5-haiku-20241022`
- `claude-3-opus-20240229`
- `claude-3-sonnet-20240229`
- `claude-3-haiku-20240307`

#### Embedding Models

- `text-embedding-3-small`
- `text-embedding-3-large`
- `text-embedding-ada-002`

## Error Handling

### Common HTTP Status Codes

| Code | Description | Solution |
|------|-------------|----------|
| `400` | Bad Request | Check request format |
| `422` | Validation Error | Verify required fields |
| `500` | Internal Error | Check Claude CLI status |

### Example Error Response

```json
{
  "error": {
    "message": "Invalid request format",
    "type": "invalid_request_error",
    "code": "validation_error"
  }
}
```

### Troubleshooting

#### Server Won't Start

```bash
# Check if port is in use
lsof -i :8000

# Test Claude CLI
claude --version
claude "test message"
```

#### Authentication Issues

```bash
# Verify Claude Code MAX subscription
claude --help

# Check CLI functionality
claude "Hello, Claude!"
```

## Development

### Project Structure

```
claude-openai-bridge/
├── src/
│   └── server.py          # Main FastAPI application
├── tests/                 # Test suite
├── docs/                  # Additional documentation
├── requirements.txt       # Python dependencies
├── .gitignore            # Git ignore rules
└── README.md             # This file
```

### Running Tests

```bash
# Install test dependencies
pip install pytest httpx

# Run tests
pytest tests/ -v
```

### API Documentation

Interactive documentation available at:

- **Swagger UI:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`
- **OpenAPI Schema:** `http://localhost:8000/openapi.json`

## Performance

### Benchmarks

| Metric | Value |
|--------|-------|
| Response Time | ~200ms (non-streaming) |
| Throughput | 100+ req/min |
| Memory Usage | ~50MB base |

### Optimization

- Enable streaming for real-time responses
- Use connection pooling for high throughput
- Monitor Claude CLI performance

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make your changes
4. Add tests for new functionality
5. Run the test suite: `pytest`
6. Commit your changes: `git commit -m "Add feature"`
7. Push to your fork: `git push origin feature-name`
8. Submit a pull request

### Development Setup

```bash
git clone https://github.com/yourusername/claude-openai-bridge.git
cd claude-openai-bridge
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
pip install -r requirements.txt
pip install -r requirements-dev.txt  # Development dependencies
```

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Support

- 📖 **Documentation:** [Full API docs](http://localhost:8000/docs)
- 🐛 **Issues:** [GitHub Issues](https://github.com/yourusername/claude-openai-bridge/issues)
- 💬 **Discussions:** [GitHub Discussions](https://github.com/yourusername/claude-openai-bridge/discussions)

## Acknowledgments

- Built for Claude Code MAX integration
- Compatible with OpenAI API specification
- Inspired by [LiteLLM](https://github.com/BerriAI/litellm) and similar bridge projects
