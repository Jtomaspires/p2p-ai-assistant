import os
from abc import abstractmethod, ABC
from dataclasses import dataclass, field
from enum import Enum
from typing import Type, Optional, Union, Any, List

import boto3
from dotenv import load_dotenv
from google.oauth2 import service_account
from httpx import AsyncClient
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel, AnthropicModelName
from pydantic_ai.models.bedrock import BedrockConverseModel, BedrockModelName
from pydantic_ai.models.gemini import GeminiModelName
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.openai import (
    OpenAIModelName,
    OpenAIChatModel,
    OpenAIResponsesModel,
)
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.azure import AzureProvider
from pydantic_ai.providers.bedrock import BedrockProvider
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.settings import ModelSettings

from launchpad.core.nodes.base import Node
from launchpad.core.task import TaskContext

load_dotenv()


class ModelProvider(str, Enum):
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"
    BEDROCK = "bedrock"
    GOOGLE_GEMINI = "google"
    GOOGLE_VERTEX_AI = "google_vertex_ai"


@dataclass
class AgentConfig:
    model_provider: ModelProvider
    model_name: Union[
        OpenAIModelName, AnthropicModelName, GeminiModelName, BedrockModelName
    ]
    output_type: Any = str
    instructions: Optional[str] = None
    deps_type: Optional[Type[Any]] = None
    name: str | None = None
    model_settings: ModelSettings | None = None
    retries: int = 1
    output_retries: int | None = None
    tools: List = field(default_factory=list)
    builtin_tools: List = field(default_factory=list)
    instrument: bool = True


class AgentNode(Node, ABC):
    class DepsType(BaseModel):
        pass

    class OutputType(BaseModel):
        pass

    def __init__(self, task_context: TaskContext = None):
        super().__init__(task_context=task_context)

        self.__async_client = AsyncClient()
        agent_wrapper = self.get_agent_config()
        self.agent = Agent(
            model=self.__get_model_instance(
                agent_wrapper.model_provider, agent_wrapper.model_name
            ),
            output_type=agent_wrapper.output_type,
            instructions=agent_wrapper.instructions,
            deps_type=agent_wrapper.deps_type,
            name=agent_wrapper.name,
            model_settings=agent_wrapper.model_settings,
            retries=agent_wrapper.retries,
            output_retries=agent_wrapper.output_retries,
            tools=agent_wrapper.tools,
            builtin_tools=agent_wrapper.builtin_tools,
            instrument=agent_wrapper.instrument,
        )

        self.agent.instrument_all()

    @abstractmethod
    def get_agent_config(self) -> AgentConfig:
        pass

    @abstractmethod
    async def process(self, task_context: TaskContext) -> TaskContext:
        pass

    def __get_model_instance(self, provider: ModelProvider, model_name: str) -> Model:
        match provider.value:
            case provider.OPENAI.value:
                return self.__get_openai_model(model_name)
            case provider.AZURE_OPENAI.value:
                return self.__get_azure_openai_model(model_name)
            case provider.ANTHROPIC.value:
                return self.__get_anthropic_model(model_name)
            case provider.OLLAMA.value:
                return self.__get_ollama_model(model_name)
            case provider.BEDROCK.value:
                return self.__get_bedrock_model(model_name)
            case provider.GOOGLE_GEMINI.value:
                return self.__get_google_gemini_model(model_name)
            case provider.GOOGLE_VERTEX_AI.value:
                return self.__get_google_vertex_ai_model(model_name)
        return self.__get_openai_model(model_name)

    def __get_openai_model(self, model_name) -> Model:
        return OpenAIResponsesModel(model_name=model_name)

    def __get_azure_openai_model(self, model_name) -> Model:
        provider = AzureProvider(
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_key=os.getenv("AZURE_OPENAI_API_KEY"),
            api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")
        )
        return OpenAIResponsesModel(
            model_name=model_name,
            provider=provider,
        )

    def __get_anthropic_model(self, model_name: AnthropicModelName) -> Model:
        return AnthropicModel(
            model_name=model_name,
            provider=AnthropicProvider(http_client=self.__async_client),
        )

    def __get_ollama_model(self, model_name: str) -> Model:
        base_url = os.getenv("OLLAMA_BASE_URL")
        if not base_url:
            raise KeyError("OLLAMA_BASE_URL not set in .env")

        return OpenAIChatModel(
            model_name=model_name, provider=OllamaProvider(base_url=base_url)
        )

    def __get_bedrock_model(self, model_name: str) -> Model:
        aws_access_key_id = os.getenv("BEDROCK_AWS_ACCESS_KEY_ID")
        aws_secret_access_key = os.getenv("BEDROCK_AWS_SECRET_ACCESS_KEY")
        aws_region = os.getenv("BEDROCK_AWS_REGION")

        bedrock_client = boto3.client(
            "bedrock-runtime",
            region_name=aws_region,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
        )
        return BedrockConverseModel(
            model_name=model_name,
            provider=BedrockProvider(bedrock_client=bedrock_client),
        )

    def __get_google_gemini_model(self, model_name: str) -> Model:
        return GoogleModel(
            model_name=model_name,
            provider=GoogleProvider(),
        )

    def __get_google_vertex_ai_model(self, model_name: str) -> Model:
        credentials = service_account.Credentials.from_service_account_file(
            filename=os.getenv("GOOGLE_APPLICATION_CREDENTIALS", ""),
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        provider = GoogleProvider(
            credentials=credentials,
            location=os.getenv("GOOGLE_VERTEX_AI_LOCATION", "europe-west1"),
        )
        return GoogleModel(
            model_name=model_name,
            provider=provider,
        )
