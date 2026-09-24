from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class MCPTool(BaseModel):
    """Definition of an MCP tool exposed to LLM clients."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(..., description="Unique tool name")
    description: str = Field(..., description="Human-readable description for LLM usage")
    inputSchema: dict[str, Any] = Field(
        ...,
        description="JSON Schema specifying acceptable parameters for the tool",
    )


class MCPToolCallRequest(BaseModel):
    """Invocation request for an MCP tool."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(..., description="Name of the tool to invoke")
    arguments: dict[str, Any] = Field(
        default_factory=dict,
        description="Input arguments matching the tool schema",
    )


class MCPContentItem(BaseModel):
    """Individual content item in an MCP response."""

    model_config = ConfigDict(frozen=True)

    type: Literal["text", "image", "resource"] = Field(
        default="text",
        description="Content type of payload",
    )
    text: str | None = Field(default=None, description="Textual payload")
    data: str | None = Field(default=None, description="Base64 data payload for binary resources")
    mimeType: str | None = Field(default=None, description="MIME type of resource")


class MCPToolCallResponse(BaseModel):
    """Result returned from an MCP tool execution."""

    model_config = ConfigDict(frozen=True)

    content: list[MCPContentItem] = Field(
        default_factory=list,
        description="List of content elements produced by the tool",
    )
    isError: bool = Field(
        default=False,
        description="Indicates whether execution resulted in an error",
    )


class MCPRequest(BaseModel):
    """JSON-RPC 2.0 request envelope for Model Context Protocol."""

    model_config = ConfigDict(frozen=True)

    jsonrpc: Literal["2.0"] = "2.0"
    id: str | int = Field(..., description="JSON-RPC message ID")
    method: str = Field(..., description="Protocol method name")
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Parameters for the invoked method",
    )


class MCPResponse(BaseModel):
    """JSON-RPC 2.0 response envelope for Model Context Protocol."""

    model_config = ConfigDict(frozen=True)

    jsonrpc: Literal["2.0"] = "2.0"
    id: str | int | None = Field(..., description="Matching JSON-RPC request ID")
    result: dict[str, Any] | None = Field(
        default=None,
        description="Method return payload on success",
    )
    error: dict[str, Any] | None = Field(
        default=None,
        description="Error details on failure",
    )
