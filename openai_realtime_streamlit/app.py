import asyncio
import base64
import json
import threading
from asyncio import run_coroutine_threadsafe
import numpy as np
import sounddevice as sd
import streamlit as st
from datetime import datetime
import traceback

import os  # <<-- Add this line

from constants import (AUTOSCROLL_SCRIPT, DOCS, 
                      HIDE_STREAMLIT_RUNNING_MAN_SCRIPT, OAI_LOGO_URL)
from utils import DeepgramRealtime
from audio import StreamingAudioRecorder
from tools import get_current_time

st.set_page_config(layout="wide")

audio_buffer = np.array([], dtype=np.int16)
buffer_lock = threading.Lock()

# Initialize session state variables
if "show_full_events" not in st.session_state:
    st.session_state.show_full_events = False

if "debug_messages" not in st.session_state:
    st.session_state.debug_messages = []

if "audio_stream_started" not in st.session_state:
    st.session_state.audio_stream_started = False

if "recording" not in st.session_state:
    st.session_state.recording = False

if "recorder" not in st.session_state:
    st.session_state.recorder = StreamingAudioRecorder()

if "connection_status" not in st.session_state:
    st.session_state.connection_status = "disconnected"
    
# Debug logging
import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Add to your session state initialization
if "debug_messages" not in st.session_state:
    st.session_state.debug_messages = []

# Add this function to help with debugging
def add_debug_message(message):
    logger.debug(message)
    st.session_state.debug_messages.append(f"{get_current_time()}: {message}")

# Add this function to help with debugging
def add_debug_message(message):
    logger.debug(message)
    st.session_state.debug_messages.append(f"{get_current_time()}: {message}")

if "audio_stream_started" not in st.session_state:
    st.session_state.audio_stream_started = False

def audio_buffer_cb(pcm_audio_chunk):
    global audio_buffer
    with buffer_lock:
        audio_buffer = np.concatenate([audio_buffer, pcm_audio_chunk])

def sd_audio_cb(outdata, frames, time, status):
    global audio_buffer
    channels = 1
    with buffer_lock:
        if len(audio_buffer) >= frames:
            outdata[:] = audio_buffer[:frames].reshape(-1, channels)
            audio_buffer = audio_buffer[frames:]
        else:
            outdata.fill(0)

def start_audio_stream():
    with sd.OutputStream(callback=sd_audio_cb, dtype="int16", samplerate=24_000, channels=1, blocksize=2_000):
        sd.sleep(int(10e6))

@st.cache_resource(show_spinner=False)
def create_loop():
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever)
    thread.start()
    return loop, thread

st.session_state.event_loop, worker_thread = create_loop()

def run_async(coroutine):
    return run_coroutine_threadsafe(coroutine, st.session_state.event_loop).result()

@st.cache_resource(show_spinner=False)
def setup_client():
    if client := st.session_state.get("client"):
        return client
    client = DeepgramRealtime(
        event_loop=st.session_state.event_loop,
        audio_buffer_cb=audio_buffer_cb,
        debug=True
    )
    return client

st.session_state.client = setup_client()

if "recorder" not in st.session_state:
    st.session_state.recorder = StreamingAudioRecorder()
if "recording" not in st.session_state:
    st.session_state.recording = False

def toggle_recording():
    st.session_state.recording = not st.session_state.recording
    if st.session_state.recording:
        if not st.session_state.client.is_connected():
            st.error("Please connect to Deepgram first")
            st.session_state.recording = False
            return
        st.session_state.recorder.start_recording()
        st.success("Recording started")
    else:
        st.session_state.recorder.stop_recording()
        if st.session_state.client.is_connected():
            st.session_state.client.send("input_audio_buffer.commit")
        st.info("Recording stopped")

@st.fragment(run_every=1)
def audio_recorder():
    if st.session_state.recording and st.session_state.client.is_connected():
        try:
            while not st.session_state.recorder.audio_queue.empty():
                chunk = st.session_state.recorder.audio_queue.get()
                if chunk is not None:
                    encoded_chunk = base64.b64encode(chunk).decode()
                    success = st.session_state.client.send(
                        "input_audio_buffer.append", 
                        {"audio": encoded_chunk}
                    )
                    if not success:
                        st.error("Failed to send audio chunk")
                        st.session_state.recording = False
                        st.session_state.recorder.stop_recording()
                        break
        except Exception as e:
            st.error(f"Error sending audio: {str(e)}")
            st.session_state.recording = False
            st.session_state.recorder.stop_recording()


@st.fragment(run_every=1)
def logs_text_area():
    logs = st.session_state.client.logs
    if st.session_state.show_full_events:
        for _, _, log in logs:
            st.json(log, expanded=False)
    else:
        for time, event_type, log in logs:
            if event_type == "server":
                st.write(f"{time}\t:green[↓ server] {json.loads(log)['type']}")
            else:
                st.write(f"{time}\t:blue[↑ client] {json.loads(log)['type']}")
    st.components.v1.html(AUTOSCROLL_SCRIPT, height=0)

@st.fragment(run_every=1)
def response_area():
    st.markdown("**conversation**")
    st.write(st.session_state.client.transcript)

@st.fragment(run_every=1)
def audio_player():
    if not st.session_state.audio_stream_started:
        st.session_state.audio_stream_started = True
        start_audio_stream()
        
@st.cache_resource
def connect_to_client():
    with st.spinner("Connecting..."):
        try:
            if not os.getenv('DEEPGRAM_API_KEY'):
                st.error("Deepgram API key not found. Please set DEEPGRAM_API_KEY environment variable.")
                return
            
            success = run_async(st.session_state.client.connect())
            if success:
                st.session_state.connection_status = "connected"
                st.success("Connected to Deepgram API")
                # st.experimental_rerun()
            else:
                st.error("Failed to connect")
        except Exception as e:
            st.error(f"Connection error: {str(e)}")
            add_debug_message(f"Connection error: {str(e)}")

@st.fragment(run_every=1)
def audio_recorder():
    if st.session_state.recording:
        while not st.session_state.recorder.audio_queue.empty():
            chunk = st.session_state.recorder.audio_queue.get()
            if st.session_state.client.is_connected():
                st.session_state.client.send("input_audio_buffer.append", 
                                           {"audio": base64.b64encode(chunk).decode()})
            else:
                st.warning("Deepgram connection is not active. Unable to send audio.")


def connect_to_deepgram():
    with st.spinner("Connecting..."):
        try:
            if not os.getenv('DEEPGRAM_API_KEY'):
                st.error("Deepgram API key not found. Please set DEEPGRAM_API_KEY environment variable.")
                return None
            success = run_async(st.session_state.client.connect())
            if success:
                st.session_state.connection_status = "connected"
                st.success("Connected to Deepgram API")
                return True
            else:
                st.error("Failed to connect")
                return False
        except Exception as e:
            st.error(f"Connection error: {str(e)}")
            add_debug_message(f"Connection error: {str(e)}")
            return None



def st_app():
    st.markdown(HIDE_STREAMLIT_RUNNING_MAN_SCRIPT, unsafe_allow_html=True)
    main_tab, docs_tab = st.tabs(["Console", "Docs"])

    with main_tab:
        st.markdown(f"<img src='{OAI_LOGO_URL}' width='30px'/>   **Deepgram Real-time Console**", unsafe_allow_html=True)

    with st.sidebar:
        col1, col2 = st.columns([3, 1])
        with col1:
            connect_button = st.button(
                "Disconnect" if st.session_state.connection_status == "connected" else "Connect",
                type="primary"
            )
        with col2:
            if st.session_state.connection_status == "connected":
                st.success("🟢")
            else:
                st.error("🔴")
        
        if connect_button:
            if st.session_state.connection_status == "connected":
                # Disconnect logic
                try:
                    st.session_state.client.disconnect()
                    st.session_state.connection_status = "disconnected"
                    connect_to_deepgram()  # This is how you force a rerun of the block
                except Exception as e:
                    st.error(f"Error disconnecting: {str(e)}")
            else:
                # Connect logic
                    connect_to_deepgram()  # This is how you force a rerun of the block
            
# Add these helper functions if not already present
def add_debug_message(message):
    print(message)  # Console logging
    st.session_state.debug_messages.append(f"{get_current_time()}: {message}")

def get_current_time():
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]

# Initialize session state variables
if "debug_messages" not in st.session_state:
    st.session_state.debug_messages = []

if "audio_stream_started" not in st.session_state:
    st.session_state.audio_stream_started = False

if "recording" not in st.session_state:
    st.session_state.recording = False

if "recorder" not in st.session_state:
    st.session_state.recorder = StreamingAudioRecorder()

# Add error handling wrapper
def safe_run(func):
    try:
        return func()
    except Exception as e:
        st.error(f"Error: {str(e)}")
        add_debug_message(f"Error in {func.__name__}: {str(e)}")
        print(traceback.format_exc())
        return None

if __name__ == '__main__':
    st_app()