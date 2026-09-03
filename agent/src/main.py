import asyncio
import argparse
import httpx

from .config import DEEPGRAM_API_KEY, GEMINI_API_KEY, LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, SERVER_URL

from livekit import api

from pipecat.workers.runner import WorkerRunner
from pipecat.pipeline.worker import PipelineWorker
from pipecat.pipeline.worker import PipelineParams
from pipecat.pipeline.pipeline import Pipeline
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import TTSSpeakFrame
from pipecat.transports.livekit.transport import LiveKitTransport, LiveKitParams
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.google.llm import GoogleLLMService
from pipecat.services.deepgram.tts import DeepgramTTSService
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair

def create_agent_token(room_name: str) -> str:
    return (
        api.AccessToken(
            api_key=LIVEKIT_API_KEY,
            api_secret=LIVEKIT_API_SECRET,
        ).with_identity("rizzeptionist-agent") \
        .with_name("Rizzeptionist") \
        .with_grants(api.VideoGrants(
            room_join=True,
            room=room_name,
        )).to_jwt()
    )

async def run_agent(room_name:str):
    agent_token = create_agent_token(room_name)

    # Setup the Transport Layer
    transport = LiveKitTransport(
        url = LIVEKIT_URL,
        token = agent_token,
        room_name=room_name,
        params=LiveKitParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            vad_analyzer=SileroVADAnalyzer(),
        ),
    )

    stt = None

    llm = GoogleLLMService(
        api_key = GEMINI_API_KEY,
        settings=GoogleLLMService.Settings(
            model="gemini-3.5-flash-lite",
        ),
    )

    tts = DeepgramTTSService(
        api_key = DEEPGRAM_API_KEY,
        settings=DeepgramTTSService.Settings(
            voice="aura-2-helena-en"
        )
    )

    context = LLMContext(
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a friendly voice assistant. "
                    "Keep responses short and conversational."
                ),
            }
        ]
    )

    context_aggregator = LLMContextAggregatorPair(context)

    pipeline = Pipeline(
        [
            transport.input(),
            transport.output(),
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=16000,
            audio_out_sample_rate=24000,
            enable_metrics=True,
        ),
    )

    # Event Handler to check if the bot is connected to the room
    @transport.event_handler("on_connected")
    async def on_connected(transport):
        print(f"Bot connected to LiveKit room: {room_name}")

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{SERVER_URL}/api/session/ready",
                params={"room_name": room_name},
            )
        print("Ready notification:", response.status_code)
    
    @transport.event_handler("on_first_participant_joined")
    async def on_first_participant_joined(transport, participant_id):
        print(f"Participant joined: {participant_id}")

        await worker.queue_frame(
            TTSSpeakFrame(
                "Hello! I'm your voice assistant. How can I help you?"
            )
        )

    @transport.event_handler("on_participant_left")
    async def on_participant_left(transport, participant_id, reason):
        print(f"Participant left: {participant_id} (reason: {reason})")
        await worker.cancel()

    runner = WorkerRunner(handle_sigint=True)

    await runner.add_workers(worker)
    await runner.run()

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "room_name",
        help="LiveKit room name to join",
    )
    return parser.parse_args()

if __name__ == "__main__":
    args = parse_args()
    asyncio.run(run_agent(args.room_name))

