import asyncio
import logging

from livekit.agents import AutoSubscribe, JobContext, WorkerOptions, cli, llm
from livekit.agents.pipeline import VoicePipelineAgent
from livekit.plugins import aws, silero

logger = logging.getLogger("livekit-agent")

class CallCenterTools(llm.FunctionContext):
    """
    These are the tools migrated from Twilio/Bedrock logic to LiveKit FunctionContext.
    """
    @llm.ai_callable(description="استخدم هذه الأداة عندما يؤكد العميل أن مشكلته السابقة تم حلها بالكامل.")
    async def mark_ticket_resolved(self, ticket_id: str, resolution_note: str):
        logger.info(f"Ticket {ticket_id} marked resolved: {resolution_note}")
        return "تم تسجيل حل المشكلة."

    @llm.ai_callable(description="استخدم هذه الأداة عندما يقول العميل إن المشكلة لسه موجودة أو يصف مشكلة جديدة.")
    async def record_complaint(self, ticket_id: str, complaint_text: str):
        logger.info(f"Complaint recorded for {ticket_id}: {complaint_text}")
        return "تم تسجيل الشكوى."

    @llm.ai_callable(description="استخدم هذه الأداة لما العميل يطلب صراحة يتكلم مع موظف حقيقي.")
    async def transfer_to_agent(self, ticket_id: str, reason: str):
        logger.info(f"Transferring {ticket_id} to agent. Reason: {reason}")
        return "جاري تحويلك إلى موظف خدمة العملاء."

    @llm.ai_callable(description="استخدم هذه الأداة لما تكون المحادثة خلصت طبيعي وتحب تقفل المكالمة بلطف.")
    async def end_call(self, goodbye_message: str):
        logger.info(f"Ending call: {goodbye_message}")
        return "سيتم إنهاء المكالمة الآن."


async def entrypoint(ctx: JobContext):
    logger.info(f"Agent starting in room: {ctx.room.name}")
    
    # Initialize AWS Bedrock LLM and AWS Polly TTS (ar-AE Zeina)
    llm_impl = aws.LLM(model="amazon.titan-text-premier-v1:0")
    tts_impl = aws.TTS(voice="Zeina", language="ar-AE") # Actually Polly voice ID Zeina
    
    # VAD for detecting human speech
    vad_impl = silero.VAD.load()

    fnc_ctx = CallCenterTools()
    
    agent = VoicePipelineAgent(
        vad=vad_impl,
        stt=aws.STT(), # Optional if we use AWS STT or we can use another provider
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
