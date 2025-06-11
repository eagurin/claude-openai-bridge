import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch
import json

from src.server import app


client = TestClient(app)


class TestHealthEndpoint:
    """Test health check functionality."""
    
    def test_health_check(self):
        """Test basic health check endpoint."""
        response = client.get("/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data
        assert data["dependencies_installed"] is True


class TestModelsEndpoint:
    """Test model listing functionality."""
    
    def test_list_models(self):
        """Test listing available models."""
        response = client.get("/v1/models")
        assert response.status_code == 200
        
        data = response.json()
        assert data["object"] == "list"
        assert "data" in data
        assert len(data["data"]) > 0
        
        # Check first model structure
        model = data["data"][0]
        assert "id" in model
        assert "object" in model
        assert "created" in model
        assert "owned_by" in model
    
    def test_get_specific_model(self):
        """Test getting specific model information."""
        model_id = "claude-3-5-sonnet-20241022"
        response = client.get(f"/v1/models/{model_id}")
        assert response.status_code == 200
        
        data = response.json()
        assert data["id"] == model_id
        assert data["object"] == "model"
        assert "capabilities" in data
        assert "limits" in data
    
    def test_get_nonexistent_model(self):
        """Test getting non-existent model returns 404."""
        response = client.get("/v1/models/nonexistent-model")
        assert response.status_code == 404


class TestChatCompletions:
    """Test chat completion functionality."""
    
    @patch('src.server.bridge_adapter.execute_claude_request')
    def test_chat_completion_basic(self, mock_execute):
        """Test basic chat completion."""
        # Mock Claude response
        mock_execute.return_value = {
            "response": "Hello! How can I help you today?",
            "metadata": {"cost_usd": 0.001, "duration_ms": 500}
        }
        
        request_data = {
            "model": "claude-3-5-sonnet-20241022",
            "messages": [
                {"role": "user", "content": "Hello!"}
            ],
            "max_tokens": 100
        }
        
        response = client.post("/v1/chat/completions", json=request_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["object"] == "chat.completion"
        assert "id" in data
        assert "created" in data
        assert data["model"] == request_data["model"]
        assert len(data["choices"]) == 1
        assert data["choices"][0]["message"]["role"] == "assistant"
        assert "usage" in data
    
    def test_chat_completion_validation_error(self):
        """Test validation error handling."""
        # Missing required 'messages' field
        request_data = {
            "model": "claude-3-5-sonnet-20241022"
        }
        
        response = client.post("/v1/chat/completions", json=request_data)
        assert response.status_code == 422
        
        data = response.json()
        assert "detail" in data
    
    def test_chat_completion_with_system_message(self):
        """Test chat completion with system message."""
        with patch('src.server.bridge_adapter.execute_claude_request') as mock_execute:
            mock_execute.return_value = {
                "response": "I'm a helpful assistant.",
                "metadata": {}
            }
            
            request_data = {
                "model": "claude-3-5-sonnet-20241022",
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "Who are you?"}
                ]
            }
            
            response = client.post("/v1/chat/completions", json=request_data)
            assert response.status_code == 200
            
            # Verify system message was processed
            mock_execute.assert_called_once()
    
    def test_chat_completion_streaming_header(self):
        """Test that streaming requests return correct content type."""
        with patch('src.server.bridge_adapter.execute_claude_request'):
            request_data = {
                "model": "claude-3-5-sonnet-20241022",
                "messages": [{"role": "user", "content": "Hello!"}],
                "stream": True
            }
            
            response = client.post("/v1/chat/completions", json=request_data)
            assert response.status_code == 200
            assert response.headers["content-type"] == "text/event-stream; charset=utf-8"


class TestEmbeddings:
    """Test embeddings functionality."""
    
    @patch('src.server.embedding_adapter.create_embeddings')
    def test_create_embeddings(self, mock_create):
        """Test basic embeddings creation."""
        # Mock embedding response
        from src.server import EmbeddingResponse, EmbeddingData, EmbeddingUsage
        
        mock_create.return_value = EmbeddingResponse(
            object="list",
            data=[
                EmbeddingData(
                    object="embedding",
                    embedding=[0.1, 0.2, 0.3],
                    index=0
                )
            ],
            model="text-embedding-3-small",
            usage=EmbeddingUsage(prompt_tokens=5, total_tokens=5)
        )
        
        request_data = {
            "input": "Hello world",
            "model": "text-embedding-3-small"
        }
        
        response = client.post("/v1/embeddings", json=request_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["object"] == "list"
        assert len(data["data"]) == 1
        assert "embedding" in data["data"][0]
        assert "usage" in data


class TestErrorHandling:
    """Test error handling across endpoints."""
    
    def test_invalid_json(self):
        """Test handling of invalid JSON."""
        response = client.post(
            "/v1/chat/completions",
            data="invalid json",
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422
    
    def test_missing_content_type(self):
        """Test handling of missing content type."""
        response = client.post(
            "/v1/chat/completions",
            data='{"model": "test"}'
        )
        assert response.status_code == 422
    
    @patch('src.server.bridge_adapter.execute_claude_request')
    def test_claude_cli_error(self, mock_execute):
        """Test handling of Claude CLI errors."""
        from fastapi import HTTPException
        
        mock_execute.side_effect = HTTPException(
            status_code=500,
            detail="Claude CLI failed"
        )
        
        request_data = {
            "model": "claude-3-5-sonnet-20241022",
            "messages": [{"role": "user", "content": "Hello!"}]
        }
        
        response = client.post("/v1/chat/completions", json=request_data)
        assert response.status_code == 500


class TestRootEndpoint:
    """Test root information endpoint."""
    
    def test_root_endpoint(self):
        """Test root endpoint returns server info."""
        response = client.get("/")
        assert response.status_code == 200
        
        data = response.json()
        assert data["name"] == "Claude OpenAI Server"
        assert "version" in data
        assert "endpoints" in data
        assert "features" in data
        assert "integration" in data


class TestCORS:
    """Test CORS configuration."""
    
    def test_cors_headers(self):
        """Test that CORS headers are present."""
        response = client.options("/v1/models")
        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers


@pytest.fixture
def mock_claude_cli():
    """Fixture to mock Claude CLI responses."""
    with patch('asyncio.create_subprocess_exec') as mock_subprocess:
        mock_process = AsyncMock()
        mock_process.communicate.return_value = (
            b"Test response from Claude",
            b"# Session: test | Cost: $0.001 | Time: 0.5s"
        )
        mock_process.returncode = 0
        mock_subprocess.return_value = mock_process
        yield mock_subprocess


class TestIntegration:
    """Integration tests with mocked Claude CLI."""
    
    def test_full_chat_flow(self, mock_claude_cli):
        """Test complete chat completion flow."""
        request_data = {
            "model": "claude-3-5-sonnet-20241022",
            "messages": [
                {"role": "system", "content": "You are helpful."},
                {"role": "user", "content": "Say hello"}
            ],
            "temperature": 0.7,
            "max_tokens": 50
        }
        
        response = client.post("/v1/chat/completions", json=request_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["choices"][0]["message"]["content"] == "Test response from Claude"
        assert data["usage"]["total_tokens"] > 0