import asyncio
import logging

from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, cli, llm
from livekit.agents.pipeline import VoicePipelineAgent
from livekit.plugins import aws, silero, deepgram

from app.conversation_state import get_state

logger = logging.getLogger("livekit-agent")

class CallCenterTools(llm.FunctionContext):
    """
    These are the tools migrated from Twilio/Bedrock logic to LiveKit FunctionContext.
    """
    def __init__(self, call_id: str):
        super().__init__()
        self.call_id = call_id

    @llm.ai_callable(description="استخدم هذه الأداة عندما يؤكد العميل أن مشكلته السابقة تم حلها بالكامل.")
    async def mark_ticket_resolved(self, ticket_id: str, resolution_note: str):
        state = get_state(self.call_id)
        if state:
            state["resolution"] = "resolved_first_call"
            state["sentiment"] = "positive"
            state["tools_used"].append("mark_ticket_resolved")
        logger.info(f"Ticket {ticket_id} marked resolved: {resolution_note}")
        return "تم تسجيل حل المشكلة."

    @llm.ai_callable(description="استخدم هذه الأداة عندما يقول العميل إن المشكلة لسه موجودة أو يصف مشكلة جديدة.")
    async def record_complaint(self, ticket_id: str, complaint_text: str):
        state = get_state(self.call_id)
        if state:
            state["resolution"] = "unresolved_complaint"
            state["sentiment"] = "frustrated"
            state["tools_used"].append("record_complaint")
        logger.info(f"Complaint recorded for {ticket_id}: {complaint_text}")
        return "تم تسجيل الشكوى."

    @llm.ai_callable(description="استخدم هذه الأداة لما العميل يطلب صراحة يتكلم مع موظف حقيقي.")
    async def transfer_to_agent(self, ticket_id: str, reason: str):
        state = get_state(self.call_id)
        if state:
            state["resolution"] = "transferred_to_agent"
            state["tools_used"].append("transfer_to_agent")
        logger.info(f"Transferring {ticket_id} to agent. Reason: {reason}")
        return "جاري تحويلك إلى موظف خدمة العملاء."

    @llm.ai_callable(description="استخدم هذه الأداة لما تكون المحادثة خلصت طبيعي وتحب تقفل المكالمة بلطف.")
    async def end_call(self, goodbye_message: str):
        state = get_state(self.call_id)
        if state:
            state["resolution"] = state.get("resolution") or "call_ended"
            state["ended"] = True
            state["tools_used"].append("end_call")
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
