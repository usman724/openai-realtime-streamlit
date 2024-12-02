import asyncio
import base64
import json
import numpy as np
import atexit
import os
import traceback
import tzlocal
from datetime import datetime
from deepgram import DeepgramClient, LiveTranscriptionEvents, LiveOptions, DeepgramClientOptions

# # assuming that st has been imported above
# if "connection_status" not in st.session_state:
#     st.session_state.connection_status = "disconnected"

class DeepgramRealtime:
    def __init__(self, event_loop=None, audio_buffer_cb=None, debug=False):
        self.debug = debug
        self.event_loop = event_loop
        self.logs = []
        self.transcript = ""
        self.connection = None
        self.audio_buffer_cb = audio_buffer_cb
        self.tools = {}
        config = DeepgramClientOptions(options={"keepalive": "60"})
        self.dg_client = DeepgramClient(config=config)
        self.is_finals = []
        self._parent = self

    def log_event(self, dev_type, event_data):
        current_time = datetime.now().strftime('%H:%M:%S')
        event_payload = json.dumps(event_data)
        self.logs.append((current_time, dev_type, event_payload))
        if self.debug:
            print(f"{current_time} - {dev_type}: {event_payload}")

    def on_message(self, socket, result):
        sentence = result.channel.alternatives[0].transcript
        if len(sentence) == 0:
            return
        if result.is_final:
            self._parent.is_finals.append(sentence)
            if result.speech_final:
                utterance = " ".join(self._parent.is_finals)
                self._parent.transcript += utterance + "\n"
                self._parent.is_finals = []
                self._parent.log_event("server", {
                    "type": "transcript_final", 
                    "text": utterance
                })
            else:
                self._parent.log_event("server", {
                    "type": "transcript_interim_final", 
                    "text": sentence
                })
        else:
            self._parent.log_event("server", {
                "type": "transcript_interim", 
                "text": sentence
            })
        
    async def connect(self, language='en-US', model='nova-2'):
        if self.is_connected():
            print("Already connected")
            return False

        try:
            print("Attempting to connect...")
            options = LiveOptions(
                model=model,
                language=language,
                smart_format=True,
                encoding="linear16",
                channels=1,
                sample_rate=24000,
                interim_results=True,
                utterance_end_ms="1000",
                vad_events=True,
                endpointing=300
            )

            self.connection = self.dg_client.listen.live.v("1")
        
            def on_open(socket, data):
                print("Connection Open")
                self._parent.log_event("server", {"type": "connection_open"})

            def on_message(socket, result):
                sentence = result.channel.alternatives[0].transcript
                if len(sentence) == 0:
                    return
                if result.is_final:
                    self._parent.is_finals.append(sentence)
                    if result.speech_final:
                        utterance = " ".join(self._parent.is_finals)
                        self._parent.transcript += utterance + " "
                        self._parent.is_finals = []
                        self._parent.log_event("server", {"type": "transcript_final", "text": utterance})
                    else:
                        self._parent.log_event("server", {"type": "transcript_interim_final", "text": sentence})
                else:
                    self._parent.log_event("server", {"type": "transcript_interim", "text": sentence})

            def on_error(socket, error):
                print(f"Server error: {error}")
                self._parent.log_event("server", {"type": "error", "error": str(error)})

            def on_close(socket, close):
                print("Connection Closed")
                self._parent.log_event("server", {"type": "connection_closed"})
                
            # Add event handlers
            self.connection.on(LiveTranscriptionEvents.Open, on_open)
            self.connection.on(LiveTranscriptionEvents.Transcript, on_message)
            self.connection.on(LiveTranscriptionEvents.Error, on_error)
            self.connection.on(LiveTranscriptionEvents.Close, on_close)

            # Start connection
            if not self.connection.start(options):
                raise Exception("Failed to start Deepgram connection")

            return True

        except Exception as e:
            print(f"Connection error: {e}")
            self.connection = None
            return False

    def is_connected(self):
        return self.connection is not None and hasattr(self.connection, 'websocket')

    def send(self, event_name, data=None):
        if not self.is_connected():
            print("Not connected to Deepgram")
            return False

        try:
            if event_name == "input_audio_buffer.append" and "audio" in data:
                audio_chunk = base64.b64decode(data["audio"])
                if self.connection:
                    print(f"Sending audio chunk of size: {len(audio_chunk)}")
                    self.connection.send(audio_chunk)
                    self.log_event("client", {
                        "type": "audio_sent", 
                        "size": len(audio_chunk)
                    })
                    return True
            elif event_name == "input_audio_buffer.commit":
                if self.connection:
                    print("Committing audio buffer")
                    self.connection.finish()
                    self.log_event("client", {"type": "audio_commit"})
                    return True
            else:
                event = {"type": event_name, **(data or {})}
                self.log_event("client", event)
                return True
        except Exception as e:
            print(f"Error sending data: {e}")
            traceback.print_exc()
            return False

    def disconnect(self):
        if self.connection:
            try:
                self.connection.finish()
            except Exception as e:
                print(f"Error disconnecting: {e}")
            finally:
                self.connection = None
        return True

    def cleanup():
        if hasattr(st.session_state, 'client') and st.session_state.client:
            st.session_state.client.disconnect()

    atexit.register(cleanup)