import json
import logging
import os
from enum import Enum
from textwrap import dedent
from typing import Optional, Union, List, Any
from pydantic import create_model

import litellm
import tenacity
from litellm.exceptions import (
    BadRequestError,
    NotFoundError,
    AuthenticationError,
    APIError,
)
from pydantic import BaseModel, Field, model_validator, ValidationError

from moatless.completion.model import Completion, StructuredOutput
from moatless.exceptions import CompletionRejectError, CompletionRuntimeError

logger = logging.getLogger(__name__)


class LLMResponseFormat(str, Enum):
    TOOLS = "tool_call"
    JSON = "json"
    ANTHROPIC_TOOLS = "anthropic_tools"
    REACT = "react"


class CompletionResponse(BaseModel):
    """Container for completion responses that can include multiple structured outputs and text"""

    structured_outputs: List[StructuredOutput] = Field(default_factory=list)
    text_response: Optional[str] = Field(default=None)
    completion: Optional[Completion] = Field(default=None)

    @classmethod
    def create(
        cls,
        text: str | None = None,
        output: List[StructuredOutput] | StructuredOutput | None = None,
        completion: Completion | None = None,
    ) -> "CompletionResponse":
        if isinstance(output, StructuredOutput):
            outputs = [output]
        elif isinstance(output, list):
            outputs = output
        else:
            outputs = None

        return cls(
            text_response=text, structured_outputs=outputs, completion=completion
        )

    @property
    def structured_output(self) -> Optional[StructuredOutput]:
        """Get the first structured output"""
        if len(self.structured_outputs) > 1:
            ignored_outputs = [
                output.__class__.__name__ for output in self.structured_outputs[1:]
            ]
            logger.warning(
                f"Multiple structured outputs found in completion response, returning {self.structured_outputs[0].__class__.__name__} and ignoring: {ignored_outputs}"
            )
        return self.structured_outputs[0] if self.structured_outputs else None


class CompletionModel(BaseModel):
    model: str = Field(..., description="The model to use for completion")
    temperature: float = Field(0.0, description="The temperature to use for completion")
    max_tokens: int = Field(
        2000, description="The maximum number of tokens to generate"
    )
    timeout: float = Field(
        120.0, description="The timeout in seconds for completion requests"
    )
    model_base_url: Optional[str] = Field(
        default=None, description="The base URL for the model API"
    )
    model_api_key: Optional[str] = Field(
        default=None, description="The API key for the model", exclude=True
    )
    api_version: Optional[str] = Field(
        default=None, description="The Azure OpenAI API version"
    ) #wwh add
    response_format: Optional[LLMResponseFormat] = Field(
        None, description="The response format expected from the LLM"
    )
    stop_words: Optional[list[str]] = Field(
        default=None, description="The stop words to use for completion"
    )
    metadata: Optional[dict] = Field(
        default=None, description="Additional metadata for the completion model"
    )
    thoughts_in_action: bool = Field(
        default=False,
        description="Whether to include thoughts in the action or in the message",
    )

    def clone(self, **kwargs) -> "CompletionModel":
        """Create a copy of the completion model with optional parameter overrides.

        Args:
            **kwargs: Parameters to override in the cloned model

        Returns:
            A new CompletionModel instance with the specified overrides
        """
        model_data = self.model_dump()
        model_data.update(kwargs)
        return CompletionModel.model_validate(model_data)

    def create_completion(
        self,
        messages: List[dict],
        system_prompt: str,
        response_model: List[type[StructuredOutput]] | type[StructuredOutput],
    ) -> CompletionResponse:
        # print("[🧪 response_model type]", type(response_model))
        # print("[🧪 raw response_model content]", response_model)
        if not response_model:
            raise CompletionRuntimeError(f"Response model is required for completion")

        if isinstance(response_model, list) and len(response_model) > 1:
            available_actions = [
                action for action in response_model if hasattr(action, "name")
            ]
            if not available_actions:
                raise CompletionRuntimeError(f"No actions found in {response_model}")
            

            # ✅ 外部传入 Action 实例列表
            from moatless.actions.action import Action
            
            valid_actions = [a for a in available_actions if hasattr(type(a), "args_schema")]

            if not valid_actions:
                raise RuntimeError("No valid actions found in `available_actions`.")

            ActionUnionType = Union[tuple(type(a).args_schema for a in valid_actions)]


            # ✅ 动作验证器
            def validate_action_type(cls, data: dict) -> dict:
                if not isinstance(data, dict):
                    raise TypeError("Expected dictionary input")

                action_type = data.get("action_type")
                if not action_type:
                    raise ValueError("Missing 'action_type' field")

                # ✅ 找到匹配的 Action 实例
                action_obj = next((a for a in valid_actions if a.name == action_type), None)
                if not action_obj:
                    valid_names = [a.name for a in valid_actions]
                    raise ValueError(
                        f"Unknown action type: {action_type}. Available: {', '.join(valid_names)}"
                    )

                action_data = data.get("action")
                if not action_data:
                    raise ValueError("Missing 'action' field")

                try:
                    schema_cls = type(action_obj).args_schema
                    data["action"] = schema_cls.model_validate(action_data)
                    return data
                except Exception as e:
                    raise ValidationError(f"Failed to validate '{action_type}' args: {e}")

            # ✅ 构造最终 Pydantic 模型（结构化响应入口）
            TakeAction = create_model(
                "TakeAction",
                __base__=StructuredOutput,  # 如果你继承的是 StructuredOutput，而不是 BaseModel
                action=(ActionUnionType, ...),
                action_type=(str, ...),
                __validators__={
                    "validate_action": model_validator(mode="before")(validate_action_type)
                }
            )
            
            #         # Create Union[...] type dynamically
            # ActionUnionType = Union[tuple(available_actions)]

            # # Define validator dynamically
            # def validate_action_type(cls, data: dict) -> dict:
            #     if not isinstance(data, dict):
            #         raise ValidationError("Expected dictionary input")

            #     action_type = data.get("action_type")
            #     if not action_type:
            #         return data

            #     action_class = next(
            #         (action for action in available_actions if action.name == action_type),
            #         None,
            #     )
            #     if not action_class:
            #         action_names = [a.name for a in available_actions]
            #         raise ValidationError(
            #             f"Unknown action type: {action_type}. "
            #             f"Available: {', '.join(action_names)}"
            #         )

            #     action_data = data.get("action")
            #     if not action_data:
            #         raise ValidationError("Action data is required")

            #     data["action"] = action_class.model_validate(action_data)
            #     return data

            # # Dynamically create Pydantic model with validator
            
            # TakeAction = create_model(
            #     "TakeAction",
            #     __base__=StructuredOutput,
            #     action=(ActionUnionType, ...),
            #     action_type=(str, ...),
            #     __validators__={"validate_action": model_validator(mode="before")(validate_action_type)},
            # )

            
            # class TakeAction(StructuredOutput):
            #     action: Union[tuple(response_model)] = Field(...)
            #     action_type: str = Field(
            #         ..., description="The type of action being taken"
            #     )

            #     @model_validator(mode="before")
            #     def validate_action(cls, data: dict) -> dict:
            #         if not isinstance(data, dict):
            #             raise ValidationError("Expected dictionary input")

            #         action_type = data.get("action_type")
            #         if not action_type:
            #             return data

            #         # Find the correct action class based on action_type
            #         action_class = next(
            #             (
            #                 action
            #                 for action in available_actions
            #                 if action.name == action_type
            #             ),
            #             None,
            #         )
            #         if not action_class:
            #             action_names = [action.name for action in available_actions]
            #             # wwh edit
            #             raise  ValueError(
            #                 f"Unknown action type: {action_type}. Available actions: {', '.join(action_names)}"
            #             )
                        
            #             # ValidationError(
            #             #         f"Unknown action type: {action_type}. Available actions: {', '.join(action_names)}"
            #             #     )

            #         # Validate the action data using the specific action class
            #         action_data = data.get("action")
            #         if not action_data:
            #             raise ValidationError("Action data is required")

            #         data["action"] = action_class.model_validate(action_data)
            #         return data
            

            response_model = TakeAction
            # print(f"生成的TakeAction内容：{response_model.model_json_schema()}")

        system_prompt += dedent(f"""\n# Response format
        You must respond with only a JSON object that match the following json_schema:\n

        {json.dumps(response_model.model_json_schema(), indent=2, ensure_ascii=False)}

        Make sure to return an instance of the JSON, not the schema itself.
    
        """)
        # FindFunction,
        # You must choose exactly one action_type from the following:
        # [RunTests, Finish, Reject, TriggerPoC, ExtractFunctionSource, GeneratePoCInput]
        # Do not invent your own tool names. 'action_type' must exactly match the above '[...]' One of the names in '.

#         system_prompt += """
#         Example:
#         To extract the function test from main.cpp:
#         {
#         "action_type": "ExtractFunctionSource",
#         "action": {
#             "file": "main.cpp",
#             "name": "test"
#         }
#         }
# """
        messages.insert(0, {"role": "system", "content": system_prompt})
        # print(f"\n🧠 [Prompt to LLM] {messages}")


        retries = tenacity.Retrying(
            retry=tenacity.retry_if_not_exception_type(
                (APIError, BadRequestError, NotFoundError, AuthenticationError)
            ),
            stop=tenacity.stop_after_attempt(3),
        )

        def _do_completion():
            completion_response = None

            try:
                completion_response = self._litellm_base_completion(
                    messages=messages, response_format={"type": "json_object"}
                )
                
                # print(f"\n[completion_response]:\n{completion_response}")

                if not completion_response or not completion_response.choices:
                    raise CompletionRuntimeError(
                        "No completion response or choices returned"
                    )

                if isinstance(
                    completion_response.choices[0].message.content, BaseModel
                ):
                    assistant_message = completion_response.choices[
                        0
                    ].message.content.model_dump()
                else:
                    assistant_message = completion_response.choices[0].message.content

                if not assistant_message:
                    raise CompletionRuntimeError("Empty response from model")
                print(f"[🏃assistant_message]:\n{assistant_message}")

                messages.append({"role": "assistant", "content": assistant_message})

                #wwh edit
                response = response_model.model_validate_json(assistant_message)
                # print(f"[response]:\n{response}")

                completion = Completion.from_llm_completion(
                    input_messages=messages,
                    completion_response=completion_response,
                    model=self.model,
                )
                if hasattr(response, "action") :
                    return CompletionResponse.create(
                        output=response.action, completion=completion
                    )
    #             if hasattr(response, "action") and hasattr(response, "action_type"):
    # # 修复：把结构动作名写入 action 实例
    #                 # response.action.name = response.action_type
    #                 return CompletionResponse.create(
    #                     output=response.action, completion=completion
    #                 )

                return CompletionResponse.create(output=response, completion=completion)

            except (ValidationError, json.JSONDecodeError) as e:
                logger.warning(
                    f"Completion attempt failed with error: {e}. Will retry."
                )
                messages.append(
                    {
                        "role": "user",
                        "content": f"The response was invalid. Fix the errors, exceptions found\n{e}",
                    }
                )
                raise CompletionRejectError(
                    message=str(e),
                    last_completion=completion_response,
                    messages=messages,
                ) from e
            except Exception as e:
                logger.exception(
                    f"Completion attempt failed with error: {e}. Will retry."
                )
                raise CompletionRuntimeError(
                    f"Failed to get completion response: {e}",
                )

        try:
            return retries(_do_completion)
        except tenacity.RetryError as e:
            raise e.reraise()

    def _litellm_base_completion(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        tool_choice: str | None = None,
        response_format: dict | None = None,
    ) -> Any:
        """Base method for making litellm completion calls with common parameters.

        Args:
            messages: List of message dictionaries
            tools: Optional list of tool definitions for function calling
            tool_choice: Optional tool choice configuration
            response_format: Optional response format configuration

        Returns:
            The completion response from litellm
        """
        litellm.drop_params = True

        @tenacity.retry(
            stop=tenacity.stop_after_attempt(2),
            wait=tenacity.wait_exponential(multiplier=3),
            retry=tenacity.retry_if_exception_type(Exception),
            reraise=True,
            before_sleep=lambda retry_state: logger.warning(
                f"Retrying litellm completion after error: {retry_state.outcome.exception()}"
            ),
        )
        def _do_completion():
            return litellm.completion(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                messages=messages,
                metadata=self.metadata or {},
                timeout=self.timeout,
                api_base=self.model_base_url,
                api_key=self.model_api_key,
                api_version=self.api_version,#wwh add
                stop=self.stop_words,
                tools=tools,
                tool_choice=tool_choice,
                response_format=response_format,
                request_timeout=self.timeout,
            )

        try:
            return _do_completion()
        except tenacity.RetryError as e:
            last_exception = e.last_attempt.exception()
            if isinstance(last_exception, litellm.APIError):
                logger.error(
                    "LiteLLM API Error: %s\nProvider: %s\nModel: %s\nStatus: %d\nDebug Info: %s\nRetries: %d/%d",
                    last_exception.message,
                    last_exception.llm_provider,
                    last_exception.model,
                    last_exception.status_code,
                    last_exception.litellm_debug_info,
                    last_exception.num_retries or 0,
                    last_exception.max_retries or 0,
                )
            else:
                logger.warning(
                    "LiteLLM completion failed after retries with error: %s",
                    str(last_exception),
                    exc_info=last_exception,
                )
            raise last_exception

    def model_dump(self, **kwargs):
        dump = super().model_dump(**kwargs)
        if "model_api_key" in dump:
            dump["model_api_key"] = None
        if "response_format" in dump:
            if dump.get("response_format") is not None:
                dump["response_format"] = dump["response_format"].value
        return dump

    @classmethod
    def model_validate(cls, obj):
        if isinstance(obj, dict) and "response_format" in obj:
            if "claude-3-5" in obj["model"]:
                from moatless.completion.anthropic import AnthtropicCompletionModel

                return AnthtropicCompletionModel(**obj)

            response_format = LLMResponseFormat(obj["response_format"])
            obj["response_format"] = response_format

            if response_format == LLMResponseFormat.TOOLS:
                from moatless.completion.tool_call import ToolCallCompletionModel

                return ToolCallCompletionModel(**obj)
            elif response_format == LLMResponseFormat.REACT:
                from moatless.completion.react import ReActCompletionModel

                return ReActCompletionModel(**obj)

        return cls(**obj)

    @model_validator(mode="after")
    def set_api_key(self) -> "CompletionModel":
        """
        Update the model with the API key from en vars if model base URL is set but API key is not as we don't persist the API key.
        """
        if self.model_base_url and not self.model_api_key:
            self.model_api_key = os.getenv("CUSTOM_LLM_API_KEY")

        return self
