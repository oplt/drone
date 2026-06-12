from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from backend.modules.ai.schemas import (
    LlamaCppCommandRequest,
    LLMChatTestRequest,
    LLMConnectionTestRequest,
    LLMModelsResponse,
    LLMProfileCreate,
    LLMProfilesResponse,
    LLMProfileUpdate,
    LLMProvidersResponse,
    LLMRoutingUpdate,
    LLMSettingsUpdate,
)
from backend.modules.ai.service import PROVIDERS, AISettingsService, llm_error_payload
from backend.modules.settings.repository import SettingsRepository
from backend.modules.settings.service import get_runtime_settings

router = APIRouter(prefix="/api/ai/llm", tags=["ai"])


@router.get("/settings")
async def get_llm_settings():
    return await AISettingsService().get_settings()


@router.put("/settings")
async def put_llm_settings(payload: LLMSettingsUpdate, request: Request):
    service = AISettingsService()
    try:
        saved = await service.save_settings(payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "INVALID_LLM_CONFIG", "message": str(exc)},
        ) from exc
    request.app.state.settings_doc = await service.repo.get_effective_settings_doc()
    request.app.state.settings = await get_runtime_settings(service.repo)
    return saved


@router.get("/providers", response_model=LLMProvidersResponse)
async def get_llm_providers():
    return LLMProvidersResponse(providers=list(PROVIDERS.values()))


@router.get("/profiles", response_model=LLMProfilesResponse)
async def get_llm_profiles():
    return await AISettingsService().list_profiles()


@router.post("/profiles")
async def create_llm_profile(payload: LLMProfileCreate, request: Request):
    service = AISettingsService()
    try:
        profile = await service.create_profile(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    request.app.state.settings_doc = await service.repo.get_effective_settings_doc()
    request.app.state.settings = await get_runtime_settings(service.repo)
    return profile


@router.put("/profiles/{profile_id}")
async def update_llm_profile(profile_id: str, payload: LLMProfileUpdate, request: Request):
    service = AISettingsService()
    try:
        profile = await service.update_profile(profile_id, payload)
    except ValueError as exc:
        status = 404 if str(exc).startswith("Unknown LLM profile") else 422
        raise HTTPException(status_code=status, detail=str(exc)) from exc
    request.app.state.settings_doc = await service.repo.get_effective_settings_doc()
    request.app.state.settings = await get_runtime_settings(service.repo)
    return profile


@router.delete("/profiles/{profile_id}", status_code=204)
async def delete_llm_profile(profile_id: str, request: Request):
    service = AISettingsService()
    try:
        await service.delete_profile(profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    request.app.state.settings_doc = await service.repo.get_effective_settings_doc()
    request.app.state.settings = await get_runtime_settings(service.repo)
    return None


@router.post("/profiles/{profile_id}/test")
async def test_llm_profile(profile_id: str):
    try:
        return await AISettingsService().test_profile(profile_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=llm_error_payload(exc)) from exc


@router.get("/profiles/{profile_id}/models", response_model=LLMModelsResponse)
async def get_llm_profile_models(profile_id: str):
    try:
        profile = await AISettingsService().get_profile(profile_id)
        models = await AISettingsService().list_profile_models(profile_id)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=llm_error_payload(exc)) from exc
    return LLMModelsResponse(provider=profile.provider, models=models)


@router.post("/profiles/{profile_id}/llama-cpp/start")
async def start_llama_cpp_server(profile_id: str):
    try:
        return await AISettingsService().start_llama_cpp_server(profile_id)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=llm_error_payload(exc)) from exc


@router.post("/profiles/{profile_id}/llama-cpp/restart")
async def restart_llama_cpp_server(profile_id: str):
    try:
        return await AISettingsService().restart_llama_cpp_server(profile_id)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=llm_error_payload(exc)) from exc


@router.post("/profiles/{profile_id}/llama-cpp/start-test")
async def start_and_test_llama_cpp_server(profile_id: str):
    try:
        return await AISettingsService().start_and_test_llama_cpp_server(profile_id)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=llm_error_payload(exc)) from exc


@router.post("/llama-cpp/stop")
async def stop_llama_cpp_server():
    return await AISettingsService().stop_llama_cpp_server()


@router.get("/llama-cpp/status")
async def get_llama_cpp_server_status():
    return await AISettingsService().llama_cpp_server_status()


@router.post("/llama-cpp/parse-command")
async def parse_llama_cpp_command(payload: LlamaCppCommandRequest):
    try:
        return await AISettingsService().parse_llama_cpp_command(payload)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=llm_error_payload(exc)) from exc


@router.get("/routing")
async def get_llm_routing():
    return await AISettingsService().get_routing()


@router.put("/routing")
async def put_llm_routing(payload: LLMRoutingUpdate, request: Request):
    service = AISettingsService()
    try:
        routing = await service.save_routing(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    request.app.state.settings_doc = await service.repo.get_effective_settings_doc()
    request.app.state.settings = await get_runtime_settings(service.repo)
    return routing


@router.get("/models", response_model=LLMModelsResponse)
async def get_llm_models(provider: str = Query(...)):
    try:
        models = await AISettingsService().list_models(provider)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=llm_error_payload(exc)) from exc
    return LLMModelsResponse(provider=provider, models=models)


@router.post("/test-connection")
async def test_llm_connection(payload: LLMConnectionTestRequest):
    try:
        return await AISettingsService().test_connection(payload)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=llm_error_payload(exc)) from exc


@router.post("/chat/test")
async def test_llm_chat(payload: LLMChatTestRequest):
    try:
        return await AISettingsService().chat_test(payload)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=llm_error_payload(exc)) from exc


@router.get("/local/status")
async def get_local_llm_status():
    service = AISettingsService(SettingsRepository())
    statuses = {}
    for provider in ("ollama", "llama_cpp"):
        statuses[provider] = await service.test_connection(
            LLMConnectionTestRequest(provider=provider)
        )
    return statuses
