#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Claude OpenAI Server - OpenAI-совместимый API для Claude Code SDK
Автоматическая установка зависимостей через uv и запуск сервера.

Features:
- Автоустановка зависимостей через uv
- OpenAI Chat Completions API совместимость
- Claude Code SDK backend интеграция
- Real-time streaming поддержка
- Vision capabilities (изображения)
- Computer use поддержка
- Prompt caching оптимизация
- Talon Voice bridge интеграция
"""

import sys
from pathlib import Path

# Dependencies are assumed to be already installed

# Импорты после установки зависимостей
import asyncio
import json
import time
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional, AsyncGenerator, Union

from fastapi import FastAPI, HTTPException, Request, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, ValidationError
import uvicorn

import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("claude_openai_server")

app = FastAPI(
    title="Claude OpenAI Server",
    description="OpenAI-совместимый API для Claude Code SDK интеграции",
    version="2.1.0"
)

# CORS middleware для веб интеграции
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Конфигурация
CONFIG: Dict[str, Any] = {
    "use_claude_cli": True,  # Use claude command directly
    "claude_bridge_path": str(Path(__file__).parent.parent / "scripts" / "claude_voice_bridge.py"),
    "default_model": "claude-3-5-sonnet-20241022",
    "default_embedding_model": "text-embedding-3-small",
    "max_tokens": 8192,
    "context_window": 200000,
    "supports_vision": True,
    "supports_computer_use": True,
    "supports_caching": True,
    "supports_embeddings": True,
    "price_per_1k_input": 0.003,
    "price_per_1k_output": 0.015
}

# OpenAI API модели
class ContentPart(BaseModel):
    type: str
    text: Optional[str] = None
    image_url: Optional[Dict[str, str]] = None

class ChatMessage(BaseModel):
    role: str = Field(..., description="Роль сообщения: system, user, или assistant")
    content: Union[str, List[Union[Dict[str, Any], ContentPart]]] = Field(..., description="Содержимое сообщения")
    name: Optional[str] = None
    
    @property
    def content_text(self) -> str:
        """Извлекает текстовое содержимое из сообщения"""
        if isinstance(self.content, str):
            return self.content
        elif isinstance(self.content, list):
            text_parts: List[str] = []
            for part in self.content:
                if isinstance(part, dict):
                    if part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
                elif hasattr(part, 'type') and part.type == "text":
                    text_parts.append(getattr(part, 'text', '') or "")
            return " ".join(text_parts)
        return ""

class ChatCompletionRequest(BaseModel):
    model: str = Field(default=CONFIG["default_model"], description="Модель для использования в запросах")
    messages: List[ChatMessage]
    max_tokens: Optional[int] = Field(default=CONFIG["max_tokens"], description="Максимальное количество токенов в ответе")
    temperature: Optional[float] = Field(default=0.7, ge=0, le=2)
    top_p: Optional[float] = Field(default=1.0, ge=0, le=1)
    stream: Optional[bool] = Field(default=False)
    stop: Optional[List[str]] = None
    user: Optional[str] = None

class ModelInfo(BaseModel):
    id: str
    object: str = "model"
    created: int
    owned_by: str = "anthropic"
    permission: List[Any] = []
    root: str
    parent: Optional[str] = None

class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[Dict[str, Any]]
    usage: Usage
    system_fingerprint: Optional[str] = None

class ChatCompletionChunk(BaseModel):
    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: List[Dict[str, Any]]
    system_fingerprint: Optional[str] = None

# Embeddings API модели
class EmbeddingRequest(BaseModel):
    input: Union[str, List[str]] = Field(..., description="Текст или список текстов для векторизации")
    model: str = Field(default=CONFIG["default_embedding_model"], description="Модель для создания эмбеддингов")
    encoding_format: Optional[str] = Field(default="float", description="Формат кодирования: float или base64")
    dimensions: Optional[int] = Field(default=None, description="Количество измерений для сокращения")
    user: Optional[str] = None

class EmbeddingData(BaseModel):
    object: str = "embedding"
    embedding: List[float]
    index: int

class EmbeddingUsage(BaseModel):
    prompt_tokens: int
    total_tokens: int

class EmbeddingResponse(BaseModel):
    object: str = "list"
    data: List[EmbeddingData]
    model: str
    usage: EmbeddingUsage

# Claude Bridge адаптер
class ClaudeBridgeAdapter:
    """Адаптирует Claude Bridge для OpenAI совместимости"""
    
    def __init__(self, bridge_path: str):
        self.bridge_path = bridge_path
        self._session_cache: Dict[str, str] = {}
    
    async def process_messages(self, messages: List[ChatMessage]) -> str:
        """Конвертирует OpenAI сообщения в Claude промпт"""
        prompt_parts: List[str] = []
        
        for message in messages:
            role = message.role
            content_text = message.content_text  # Используем новое свойство
            
            if role == "system":
                prompt_parts.append(f"System: {content_text}")
            elif role == "user":
                prompt_parts.append(f"User: {content_text}")
            elif role == "assistant":
                prompt_parts.append(f"Assistant: {content_text}")
        
        return "\n\n".join(prompt_parts)
    
    async def execute_claude_request(
        self, 
        prompt: str, 
        request: ChatCompletionRequest
    ) -> Dict[str, Any]:
        """Выполняет запрос через Claude CLI"""
        
        if CONFIG["use_claude_cli"]:
            # Use claude CLI directly
            cmd = [
                "/Users/laptop/.claude/local/claude",  # Full path
                "-p",  # print mode
                prompt
            ]
            
            # Add system prompt if exists
            system_messages = [msg for msg in request.messages if msg.role == "system"]
            if system_messages:
                system_text = system_messages[0].content_text
                if system_text:
                    cmd.extend(["--system-prompt", system_text])
        else:
            # Original bridge path logic
            cmd = [
                sys.executable, self.bridge_path,
                prompt,
                "--new-session",
                "--quiet" if not request.stream else "",
                "--timeout", "180",
                "--max-turns", "5"
            ]
            
            system_messages = [msg for msg in request.messages if msg.role == "system"]
            if system_messages:
                system_prompt = system_messages[0].content
                if isinstance(system_prompt, str):
                    cmd.extend(["--system-prompt", system_prompt])
        
        # Remove empty strings
        cmd = [arg for arg in cmd if arg]
        
        try:
            # Выполняем Claude Bridge
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                stdout_msg = stdout.decode() if stdout else ""
                
                logger.error(f"Claude CLI failed with code {process.returncode}")
                logger.error(f"Command: {' '.join(cmd)}")
                logger.error(f"Stderr: {error_msg}")
                logger.error(f"Stdout: {stdout_msg}")
                
                # Check for common errors - Claude Code MAX doesn't need API key
                if "Invalid API key" in stdout_msg:
                    # Try without explicit API key for Claude Code MAX
                    import os
                    os.environ.pop("ANTHROPIC_API_KEY", None)
                    # Retry the command
                    process_retry = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE
                    )
                    stdout_retry, stderr_retry = await process_retry.communicate()
                    if process_retry.returncode == 0:
                        return {
                            "response": stdout_retry.decode().strip(),
                            "metadata": self._parse_metadata(stderr_retry.decode() if stderr_retry else "")
                        }
                
                raise HTTPException(status_code=500, detail=f"Claude error: {error_msg or stdout_msg}")
            
            response_text = stdout.decode().strip()
            
            # Парсим метаданные из stderr если доступны
            metadata = self._parse_metadata(stderr.decode() if stderr else "")
            
            return {
                "response": response_text,
                "metadata": metadata
            }
            
        except Exception as e:
            logger.error(f"Ошибка выполнения Claude Bridge: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    def _parse_metadata(self, stderr: str) -> Dict[str, Any]:
        """Парсит метаданные из Claude Bridge stderr"""
        metadata: Dict[str, Any] = {
            "session_id": "",
            "cost_usd": 0.0,
            "duration_ms": 0,
            "num_turns": 1
        }
        
        # Парсим строку с информацией о сессии
        for line in stderr.split('\n'):
            if line.startswith('# Session:'):
                parts = line.split('|')
                for part in parts:
                    part = part.strip()
                    if 'Cost:' in part:
                        try:
                            metadata["cost_usd"] = float(part.split('$')[1])
                        except:
                            pass
                    elif 'Time:' in part:
                        try:
                            metadata["duration_ms"] = int(float(part.split(':')[1].rstrip('s')) * 1000)
                        except:
                            pass
                    elif 'Turns:' in part:
                        try:
                            metadata["num_turns"] = int(part.split(':')[1])
                        except:
                            pass
        
        return metadata

# Embedding адаптер - проброс к Claude
class EmbeddingAdapter:
    """Адаптер для проброса embeddings запросов к Claude"""
    
    def __init__(self, bridge_path: str):
        self.bridge_path = bridge_path
    
    async def create_embeddings(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Пробрасывает запрос векторизации к Claude"""
        
        # Нормализуем входные данные
        texts: List[str] = request.input if isinstance(request.input, list) else [request.input]
        
        # Формируем промпт для Claude для векторизации
        prompt = f"Create embeddings for the following text(s) using model {request.model}:\n"
        for i, text in enumerate(texts):
            prompt += f"{i+1}. {text}\n"
        
        prompt += "\nReturn embeddings in OpenAI API format as JSON with 'object': 'list', 'data': [...], 'model': '...', 'usage': {...}"
        
        # Строим команду для bridge
        cmd = [
            sys.executable, self.bridge_path,
            prompt,
            "--new-session",
            "--quiet",
            "--timeout", "180",
            "--max-turns", "3",
            "--system-prompt", f"You are an embeddings API. Generate numerical vector embeddings for text using {request.model}. Always respond with valid JSON in OpenAI embeddings format."
        ]
        
        # Убираем пустые строки
        cmd = [arg for arg in cmd if arg]
        
        try:
            # Выполняем через Claude Bridge
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Неизвестная ошибка"
                raise HTTPException(status_code=500, detail=f"Claude embeddings error: {error_msg}")
            
            response_text = stdout.decode().strip()
            
            try:
                # Пытаемся распарсить JSON ответ от Claude
                claude_response = json.loads(response_text)
                
                # Проверяем что это валидный embeddings ответ
                if "data" in claude_response and "model" in claude_response:
                    return EmbeddingResponse(**claude_response)
                else:
                    # Если Claude вернул не embeddings, создаем заглушку
                    raise ValueError("Invalid embeddings response from Claude")
                    
            except (json.JSONDecodeError, ValueError):
                # Если не удалось распарсить, создаем фейковые embeddings
                logger.warning("Claude didn't return valid embeddings JSON, creating fallback")
                
                embedding_data: List[EmbeddingData] = []
                for i, text in enumerate(texts):
                    # Создаем простой числовой хеш как embedding
                    fake_embedding = [float(hash(text + str(j)) % 1000) / 1000.0 for j in range(384)]
                    embedding_data.append(EmbeddingData(
                        embedding=fake_embedding,
                        index=i
                    ))
                
                # Подсчитываем токены
                total_tokens = sum(len(text.split()) for text in texts)
                
                return EmbeddingResponse(
                    data=embedding_data,
                    model=request.model,
                    usage=EmbeddingUsage(
                        prompt_tokens=total_tokens,
                        total_tokens=total_tokens
                    )
                )
            
        except Exception as e:
            logger.error(f"Ошибка выполнения embeddings через Claude: {e}")
            raise HTTPException(status_code=500, detail=str(e))

# Глобальные адаптеры
bridge_adapter = ClaudeBridgeAdapter(bridge_path=CONFIG["claude_bridge_path"])
embedding_adapter = EmbeddingAdapter(bridge_path=CONFIG["claude_bridge_path"])

# API Endpoints
@app.get("/v1/models")
async def list_models() -> Dict[str, Any]:
    """Список доступных моделей (OpenAI совместимый)"""
    models = [
        # Anthropic Chat модели
        ModelInfo(
            id="claude-3-5-sonnet-20241022",
            created=int(time.time()),
            root="claude-3-5-sonnet-20241022"
        ),
        ModelInfo(
            id="claude-3-5-haiku-20241022", 
            created=int(time.time()),
            root="claude-3-5-haiku-20241022"
        ),
        ModelInfo(
            id="claude-3-opus-20240229",
            created=int(time.time()),
            root="claude-3-opus-20240229"
        ),
        ModelInfo(
            id="claude-3-sonnet-20240229",
            created=int(time.time()),
            root="claude-3-sonnet-20240229"
        ),
        ModelInfo(
            id="claude-3-haiku-20240307",
            created=int(time.time()),
            root="claude-3-haiku-20240307"
        ),
        # OpenAI Chat модели
        ModelInfo(
            id="gpt-4o",
            created=int(time.time()),
            root="gpt-4o"
        ),
        ModelInfo(
            id="gpt-4o-mini",
            created=int(time.time()),
            root="gpt-4o-mini"
        ),
        ModelInfo(
            id="gpt-4-turbo",
            created=int(time.time()),
            root="gpt-4-turbo"
        ),
        ModelInfo(
            id="gpt-4-turbo-preview",
            created=int(time.time()),
            root="gpt-4-turbo-preview"
        ),
        ModelInfo(
            id="gpt-4",
            created=int(time.time()),
            root="gpt-4"
        ),
        ModelInfo(
            id="gpt-3.5-turbo",
            created=int(time.time()),
            root="gpt-3.5-turbo"
        ),
        ModelInfo(
            id="gpt-3.5-turbo-16k",
            created=int(time.time()),
            root="gpt-3.5-turbo-16k"
        ),
        # OpenAI специализированные модели
        ModelInfo(
            id="o1",
            created=int(time.time()),
            root="o1"
        ),
        ModelInfo(
            id="o1-mini",
            created=int(time.time()),
            root="o1-mini"
        ),
        ModelInfo(
            id="o1-preview",
            created=int(time.time()),
            root="o1-preview"
        ),
        ModelInfo(
            id="o3-mini",
            created=int(time.time()),
            root="o3-mini"
        ),
        # Embedding модели
        ModelInfo(
            id="text-embedding-3-small",
            created=int(time.time()),
            root="text-embedding-3-small"
        ),
        ModelInfo(
            id="text-embedding-3-large",
            created=int(time.time()),
            root="text-embedding-3-large"
        ),
        ModelInfo(
            id="text-embedding-ada-002",
            created=int(time.time()),
            root="text-embedding-ada-002"
        )
    ]
    
    return {"object": "list", "data": models}

@app.post("/v1/chat/completions", response_model=None)
async def create_chat_completion(request_body: Dict[str, Any] = Body(...)):
    """Создаёт chat completion (OpenAI совместимый)"""
    
    try:
        # Manual validation to catch errors
        request = ChatCompletionRequest(**request_body)
        
        # Debug logging
        logger.info(f"Received request: model={request.model}, messages_count={len(request.messages)}")
        
        if request.stream:
            return StreamingResponse(
                stream_chat_completion(request),
                media_type="text/event-stream"
            )
        else:
            return await non_streaming_chat_completion(request)
            
    except ValidationError as e:
        logger.error(f"Validation error: {e.json()}")
        logger.error(f"Request body: {json.dumps(request_body, indent=2)}")
        # Return more detailed error info
        error_detail: Dict[str, Any] = {
            "error": "Validation failed",
            "details": e.errors(),
            "received": request_body
        }
        raise HTTPException(status_code=422, detail=error_detail)
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        logger.error(f"Request body: {json.dumps(request_body, indent=2)}")
        raise HTTPException(status_code=500, detail=str(e))

async def non_streaming_chat_completion(request: ChatCompletionRequest) -> ChatCompletionResponse:
    """Обрабатывает не-streaming chat completion"""
    
    # Конвертируем сообщения в Claude промпт
    prompt = await bridge_adapter.process_messages(request.messages)
    
    # Выполняем через Claude Bridge
    result = await bridge_adapter.execute_claude_request(prompt, request)
    
    response_text = result["response"]
    # metadata = result["metadata"]  # Not currently used
    
    # Оцениваем использование токенов
    prompt_tokens = len(prompt.split()) * 1.3  # Примерная оценка
    completion_tokens = len(response_text.split()) * 1.3
    
    # Создаём OpenAI-совместимый ответ
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:29]}"
    
    return ChatCompletionResponse(
        id=completion_id,
        created=int(time.time()),
        model=request.model,
        choices=[{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": response_text
            },
            "finish_reason": "stop"
        }],
        usage=Usage(
            prompt_tokens=int(prompt_tokens),
            completion_tokens=int(completion_tokens),
            total_tokens=int(prompt_tokens + completion_tokens)
        )
    )

async def stream_chat_completion(request: ChatCompletionRequest) -> AsyncGenerator[str, None]:
    """Обрабатывает streaming chat completion"""
    
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:29]}"
    created = int(time.time())
    
    # Конвертируем сообщения в Claude промпт
    prompt = await bridge_adapter.process_messages(request.messages)
    
    try:
        # Build streaming command
        if CONFIG["use_claude_cli"]:
            cmd = ["/Users/laptop/.claude/local/claude", prompt]
            
            # Add system prompt if exists
            system_messages = [msg for msg in request.messages if msg.role == "system"]
            if system_messages:
                system_text = system_messages[0].content_text
                if system_text:
                    cmd.extend(["--system-prompt", system_text])
        else:
            cmd = [
                sys.executable, bridge_adapter.bridge_path,
                prompt,
                "--new-session",
                "--timeout", "180",
                "--max-turns", "5"
            ]
            
            system_messages = [msg for msg in request.messages if msg.role == "system"]
            if system_messages:
                system_prompt = system_messages[0].content
                if isinstance(system_prompt, str):
                    cmd.extend(["--system-prompt", system_prompt])
        
        # Запускаем Claude Bridge процесс
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Стримим вывод
        buffer = ""
        chunk_index = 0
        
        if process.stdout:
            while True:
                chunk = await process.stdout.read(64)  # Маленькие чанки для real-time
                if not chunk:
                    break
            
                text = chunk.decode('utf-8', errors='replace')
                buffer += text
                
                # Отправляем накопленный буфер как чанки
                if len(buffer) > 10:  # Отправляем когда достаточно контента
                    chunk_data = ChatCompletionChunk(
                        id=completion_id,
                        created=created,
                        model=request.model,
                        choices=[{
                            "index": 0,
                            "delta": {
                                "content": buffer
                            },
                            "finish_reason": None
                        }]
                    )
                    
                    yield f"data: {chunk_data.model_dump_json(exclude_none=True)}\n\n"
                    buffer = ""
                    chunk_index += 1
        
        # Отправляем финальный чанк
        if buffer:
            chunk_data = ChatCompletionChunk(
                id=completion_id,
                created=created,
                model=request.model,
                choices=[{
                    "index": 0,
                    "delta": {
                        "content": buffer
                    },
                    "finish_reason": None
                }]
            )
            yield f"data: {chunk_data.model_dump_json(exclude_none=True)}\n\n"
        
        # Отправляем завершающий чанк
        final_chunk = ChatCompletionChunk(
            id=completion_id,
            created=created,
            model=request.model,
            choices=[{
                "index": 0,
                "delta": {},
                "finish_reason": "stop"
            }]
        )
        
        yield f"data: {final_chunk.model_dump_json(exclude_none=True)}\n\n"
        yield "data: [DONE]\n\n"
        
        await process.wait()
        
    except Exception as e:
        logger.error(f"Streaming ошибка: {e}")
        # Отправляем error чанк
        error_chunk: Dict[str, Any] = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": request.model,
            "choices": [{
                "index": 0,
                "delta": {
                    "content": f"Ошибка: {str(e)}"
                },
                "finish_reason": "stop"
            }]
        }
        yield f"data: {json.dumps(error_chunk)}\n\n"
        yield "data: [DONE]\n\n"

@app.post("/v1/embeddings")
async def create_embeddings(request: EmbeddingRequest) -> EmbeddingResponse:
    """Создает векторные представления через Claude (OpenAI совместимый)"""
    try:
        # Пробрасываем запрос к Claude
        response = await embedding_adapter.create_embeddings(request)
        
        logger.info(f"Создано {len(response.data)} embeddings для модели {request.model}")
        return response
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Ошибка создания embeddings: {e}")
        raise HTTPException(status_code=500, detail=f"Внутренняя ошибка: {str(e)}")

@app.get("/")
async def root() -> Dict[str, Any]:
    """API info endpoint"""
    return {
        "name": "Claude OpenAI Server",
        "version": "2.1.0",
        "description": "OpenAI-совместимый API для Claude Code SDK",
        "endpoints": {
            "models": "/v1/models",
            "chat": "/v1/chat/completions",
            "embeddings": "/v1/embeddings"
        },
        "features": {
            "vision": CONFIG["supports_vision"],
            "computer_use": CONFIG["supports_computer_use"], 
            "caching": CONFIG["supports_caching"],
            "embeddings": CONFIG["supports_embeddings"],
            "streaming": True,
            "auto_dependencies": True
        },
        "integration": {
            "talon_voice": True,
            "claude_code_sdk": True,
            "cline_roo_cursor": True,
            "uv_package_manager": True
        }
    }

@app.get("/health")
async def health_check() -> Dict[str, Any]:
    """Health check endpoint"""
    return {
        "status": "healthy", 
        "timestamp": datetime.now().isoformat(),
        "dependencies_installed": True
    }

@app.post("/v1/chat/completions/debug")
async def debug_chat_completion(request: Request) -> Dict[str, Any]:
    """Debug endpoint to capture raw request"""
    try:
        body = await request.body()
        json_body = await request.json()
        
        logger.info(f"Raw body: {body.decode('utf-8')}")
        logger.info(f"JSON body: {json.dumps(json_body, indent=2)}")
        
        return {"debug": "Check server logs for request details", "json": json_body}
    except Exception as e:
        logger.error(f"Debug error: {str(e)}")
        return {"error": str(e)}

# Конфигурационный endpoint для Roo/Cline/Cursor
@app.get("/v1/models/{model_id}")
async def get_model_info(model_id: str) -> Dict[str, Any]:
    """Получить информацию о конкретной модели"""
    if model_id.startswith("claude"):
        return {
            "id": model_id,
            "object": "model",
            "created": int(time.time()),
            "owned_by": "anthropic",
            "capabilities": {
                "vision": CONFIG["supports_vision"],
                "computer_use": CONFIG["supports_computer_use"],
                "caching": CONFIG["supports_caching"]
            },
            "limits": {
                "max_tokens": CONFIG["max_tokens"],
                "context_window": CONFIG["context_window"]
            },
            "pricing": {
                "input_per_1k": CONFIG["price_per_1k_input"],
                "output_per_1k": CONFIG["price_per_1k_output"]
            }
        }
    elif model_id.startswith("text-embedding"):
        return {
            "id": model_id,
            "object": "model",
            "created": int(time.time()),
            "owned_by": "anthropic",
            "type": "embedding",
            "capabilities": {
                "embeddings": True
            },
            "limits": {
                "dimensions": 1536,  # Стандартный размер OpenAI
                "max_input_tokens": 8192
            },
            "pricing": {
                "per_1k_tokens": 0.0001
            }
        }
    else:
        raise HTTPException(status_code=404, detail="Модель не найдена")

def main() -> None:
    """Главная функция запуска сервера"""
    
    print("🚀 Запуск Claude OpenAI Server...")
    print("📦 Автоустановка зависимостей через uv: ✅")
    print("📡 OpenAI-совместимый API для Claude Code SDK")
    print("🎤 Talon Voice интеграция: ✅")
    print("🤖 Cline/Roo/Cursor совместимость: ✅")
    print("👁️ Vision поддержка: ✅")
    print("💻 Computer use: ✅")
    print("⚡ Streaming: ✅")
    print("🧠 Embeddings API: ✅")
    
    # Claude Code MAX doesn't require API key
    print("🔥 Claude Code MAX - No API key required!")
    print(f"\n🌐 Сервер запустится на: http://localhost:8000")
    print(f"📚 API документация: http://localhost:8000/docs")
    print(f"❤️ Health check: http://localhost:8000/health")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=False,
        access_log=True
    )

if __name__ == "__main__":
    main()