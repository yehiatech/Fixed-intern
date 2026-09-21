import asyncio
import logging

from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, cli, llm
from livekit.agents.pipeline import VoicePipelineAgent
from livekit.plugins import aws, silero, deepgram
import logging
logger = logging.getLogger("livekit-agent")
logger = logging.getLogger("livekit-agent")

import requests

def _update_state(call_id: str, payload: dict):
    # Using Docker internal hostname to reach the orchestrator API
    url = f"http://call-orchestrator:8001/calls/internal/state/{call_id}"
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        logger.error(f"Failed to update state for {call_id}: {e}")

class CallCenterTools(llm.FunctionContext):
    """
    These are the tools migrated from Twilio/Bedrock logic to LiveKit FunctionContext.
    """
    def __init__(self, call_id: str):
        super().__init__()
        self.call_id = call_id

    @llm.ai_callable(description="استخدم هذه الأداة عندما يؤكد العميل أن مشكلته السابقة تم حلها بالكامل.")
    async def mark_ticket_resolved(self, ticket_id: str, resolution_note: str):
        payload = {
            "resolution": "resolved_first_call",
            "sentiment": "positive",
            "tools_used": ["mark_ticket_resolved"]
        }
        await asyncio.to_thread(_update_state, self.call_id, payload)
        logger.info(f"Ticket {ticket_id} marked resolved: {resolution_note}")
        return "تم تسجيل حل المشكلة."

    @llm.ai_callable(description="استخدم هذه الأداة عندما يقول العميل إن المشكلة لسه موجودة أو يصف مشكلة جديدة.")
    async def record_complaint(self, ticket_id: str, complaint_text: str):
        payload = {
            "resolution": "unresolved_complaint",
            "sentiment": "frustrated",
            "tools_used": ["record_complaint"]
        }
        await asyncio.to_thread(_update_state, self.call_id, payload)
        logger.info(f"Complaint recorded for {ticket_id}: {complaint_text}")
        return "تم تسجيل الشكوى."

    @llm.ai_callable(description="استخدم هذه الأداة لما العميل يطلب صراحة يتكلم مع موظف حقيقي.")
    async def transfer_to_agent(self, ticket_id: str, reason: str):
        payload = {
            "resolution": "transferred_to_agent",
            "tools_used": ["transfer_to_agent"],
            "ended": True
        }
        await asyncio.to_thread(_update_state, self.call_id, payload)
        logger.info(f"Transferring {ticket_id} to agent. Reason: {reason}")
        return "جاري تحويلك إلى موظف خدمة العملاء."

    @llm.ai_callable(description="استخدم هذه الأداة لما تكون المحادثة خلصت طبيعي وتحب تقفل المكالمة بلطف.")
    async def end_call(self, goodbye_message: str):
        payload = {
            "resolution": "call_ended",
            "ended": True,
            "tools_used": ["end_call"]
        }
        await asyncio.to_thread(_update_state, self.call_id, payload)
        logger.info(f"Ending call: {goodbye_message}")
        return "سيتم إنهاء المكالمة الآن."


async def entrypoint(ctx: JobContext):
    logger.info(f"Agent starting in room: {ctx.room.name}")
    
    # Extract call_id from room name (e.g., call_12345)
    call_id = ctx.room.name.replace("call_", "") if ctx.room.name.startswith("call_") else ctx.room.name

    # Initialize AWS Bedrock LLM and AWS Polly TTS (ar-AE Zeina)
    llm_impl = aws.LLM(model="amazon.titan-text-premier-v1:0")
    tts_impl = aws.TTS(voice="Zeina", language="ar-AE") # Actually Polly voice ID Zeina
    
    # VAD for detecting human speech
    vad_impl = silero.VAD.load()

    # Use Deepgram for robust Arabic STT
    stt_impl = deepgram.STT(language="ar")

    fnc_ctx = CallCenterTools(call_id=call_id)
    
    agent = VoicePipelineAgent(
        vad=vad_impl,
        stt=stt_impl,
        llm=llm_impl,
        tts=tts_impl,
        chat_ctx=llm.ChatContext().append(
            role="system",
            text="أنت مساعد خدمة عملاء ذكي لشركة اتصالات. تحدث باللغة العربية بلهجة مصرية مهذبة."
        ),
        fnc_ctx=fnc_ctx,
    )
    
    agent.start(ctx.room)
    
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    logger.info("Agent connected to LiveKit room.")
    
    # Say hello initially
    await agent.say("مرحباً، أنا المساعد الذكي. كيف يمكنني مساعدتك اليوم؟", allow_interruptions=True)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint))
