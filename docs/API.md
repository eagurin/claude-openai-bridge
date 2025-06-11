# API Reference

## Overview

The Claude OpenAI Bridge provides a fully compatible OpenAI API interface for Claude Code MAX. All endpoints follow the OpenAI API specification exactly.

## Base URL

```
http://localhost:8000/v1
```

## Authentication

No authentication required. The server uses your Claude Code MAX subscription automatically.

For OpenAI SDK compatibility, include any non-empty string as the API key:

```bash
curl -H "Authorization: Bearer dummy" ...
```

## Rate Limits

Rate limits are managed by your Claude Code MAX subscription. The bridge itself has no additional limits.

## Content Types

All requests must include:
```
Content-Type: application/json
```

## Models

### List Models

**GET** `/v1/models`

Returns a list of available models.

#### Response

```json
{
  "object": "list",
  "data": [
    {
      "id": "claude-3-5-sonnet-20241022",
      "object": "model",
      "created": 1677610602,
      "owned_by": "anthropic",
      "permission": [],
      "root": "claude-3-5-sonnet-20241022",
      "parent": null
    }
  ]
}
```

### Retrieve Model

**GET** `/v1/models/{model}`

Retrieves information about a specific model.

#### Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `model` | string | The model identifier |

#### Response

```json
{
  "id": "claude-3-5-sonnet-20241022",
  "object": "model",
  "created": 1677610602,
  "owned_by": "anthropic",
  "capabilities": {
    "vision": true,
    "computer_use": true,
    "caching": true
  },
  "limits": {
    "max_tokens": 8192,
    "context_window": 200000
  }
}
```

## Chat Completions

### Create Chat Completion

**POST** `/v1/chat/completions`

Creates a completion for the chat message.

#### Request Body

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `model` | string | Yes | Model to use for completion |
| `messages` | array | Yes | Array of message objects |
| `max_tokens` | integer | No | Maximum tokens to generate |
| `temperature` | number | No | Sampling temperature (0-2) |
| `top_p` | number | No | Nucleus sampling parameter |
| `stream` | boolean | No | Enable streaming responses |
| `stop` | array | No | Stop sequences |
| `user` | string | No | User identifier |

#### Message Object

| Parameter | Type | Description |
|-----------|------|-------------|
| `role` | string | Role: "system", "user", or "assistant" |
| `content` | string or array | Message content |
| `name` | string | Optional name for the participant |

#### Content Array (for multimodal)

```json
{
  "role": "user",
  "content": [
    {
      "type": "text",
      "text": "What's in this image?"
    },
    {
      "type": "image_url",
      "image_url": {
        "url": "data:image/jpeg;base64,..."
      }
    }
  ]
}
```

#### Example Request

```json
{
  "model": "claude-3-5-sonnet-20241022",
  "messages": [
    {
      "role": "system",
      "content": "You are a helpful assistant."
    },
    {
      "role": "user",
      "content": "Hello!"
    }
  ],
  "max_tokens": 100,
  "temperature": 0.7
}
```

#### Response

```json
{
  "id": "chatcmpl-123",
  "object": "chat.completion",
  "created": 1677652288,
  "model": "claude-3-5-sonnet-20241022",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello! How can I assist you today?"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 20,
    "completion_tokens": 10,
    "total_tokens": 30
  }
}
```

#### Streaming Response

When `stream: true`, responses are sent as Server-Sent Events:

```
data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1677652288,"model":"claude-3-5-sonnet-20241022","choices":[{"index":0,"delta":{"content":"Hello"},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1677652288,"model":"claude-3-5-sonnet-20241022","choices":[{"index":0,"delta":{"content":"!"},"finish_reason":null}]}

data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1677652288,"model":"claude-3-5-sonnet-20241022","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

## Embeddings

### Create Embeddings

**POST** `/v1/embeddings`

Creates an embedding vector representing the input text.

#### Request Body

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `input` | string or array | Yes | Text to embed |
| `model` | string | Yes | Embedding model to use |
| `encoding_format` | string | No | Format: "float" or "base64" |
| `dimensions` | integer | No | Number of dimensions |
| `user` | string | No | User identifier |

#### Example Request

```json
{
  "input": "The quick brown fox jumps over the lazy dog",
  "model": "text-embedding-3-small",
  "encoding_format": "float"
}
```

#### Response

```json
{
  "object": "list",
  "data": [
    {
      "object": "embedding",
      "embedding": [0.0023, -0.009, 0.0055, ...],
      "index": 0
    }
  ],
  "model": "text-embedding-3-small",
  "usage": {
    "prompt_tokens": 8,
    "total_tokens": 8
  }
}
```

## Error Handling

### Error Response Format

```json
{
  "error": {
    "message": "Error description",
    "type": "error_type",
    "code": "error_code"
  }
}
```

### HTTP Status Codes

| Code | Description |
|------|-------------|
| `200` | Success |
| `400` | Bad Request |
| `422` | Validation Error |
| `500` | Internal Server Error |

### Common Errors

#### 400 Bad Request

```json
{
  "error": {
    "message": "Invalid request format",
    "type": "invalid_request_error",
    "code": "invalid_format"
  }
}
```

#### 422 Validation Error

```json
{
  "error": {
    "message": "Validation failed",
    "type": "validation_error",
    "code": "missing_field",
    "details": [
      {
        "loc": ["body", "messages"],
        "msg": "field required",
        "type": "value_error.missing"
      }
    ]
  }
}
```

#### 500 Internal Server Error

```json
{
  "error": {
    "message": "Claude CLI error: command failed",
    "type": "internal_error",
    "code": "cli_error"
  }
}
```

## Health Check

### Check Server Health

**GET** `/health`

Returns server health status.

#### Response

```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00Z",
  "dependencies_installed": true
}
```

## Versioning

The API follows semantic versioning. The current version is `v1`.

Future versions will maintain backwards compatibility where possible.

## OpenAPI Specification

The complete OpenAPI specification is available at:
- **JSON:** `http://localhost:8000/openapi.json`
- **Interactive Docs:** `http://localhost:8000/docs`
- **ReDoc:** `http://localhost:8000/redoc`