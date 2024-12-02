import os
import json
import base64
from datetime import datetime
import streamlit as st
from deepgram import DeepgramClient, PrerecordedOptions

# Page configuration
st.set_page_config(layout="wide", page_title="Deepgram Console")

# Hide Streamlit elements
st.markdown("""
<style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    .stDeployButton {display:none;}
    .block-container {padding-top: 1rem;}
    div[data-testid="stSidebarContent"] > div:first-child {padding-top: 1.5rem;}
    div[data-testid="stSidebarUserContent"] {padding-top: 0;}
    .st-emotion-cache-1629p8f h1 {padding-top: 0;}
</style>
""", unsafe_allow_html=True)

# HTML/JavaScript for audio recording
AUDIO_RECORDER_HTML = """
<div class="audio-recorder" style="margin-top: 10px;">
    <audio id="recordedAudio" style="display:none;"></audio>
    <div class="controls" style="display: flex; gap: 10px;">
        <button id="startRecord" onclick="startRecording()" 
                style="background: #262730; color: white; border: none; padding: 10px 15px; border-radius: 4px; cursor: pointer;">
            Start Recording
        </button>
        <button id="stopRecord" onclick="stopRecording()" disabled 
                style="background: #262730; color: white; border: none; padding: 10px 15px; border-radius: 4px; cursor: pointer;">
            Stop Recording
        </button>
    </div>
</div>

<script>
let mediaRecorder;
let audioChunks = [];

async function startRecording() {
    audioChunks = [];
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream);
        
        mediaRecorder.ondataavailable = (event) => {
            audioChunks.push(event.data);
        };

        mediaRecorder.onstop = () => {
            const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
            const audioUrl = URL.createObjectURL(audioBlob);
            const audio = document.getElementById('recordedAudio');
            audio.src = audioUrl;
            audio.style.display = 'block';
            
            // Convert to base64 and send to Streamlit
            const reader = new FileReader();
            reader.readAsDataURL(audioBlob);
            reader.onloadend = () => {
                const base64Audio = reader.result;
                window.parent.postMessage({
                    type: 'audio_data',
                    data: base64Audio
                }, '*');
            };
        };

        mediaRecorder.start();
        document.getElementById('startRecord').disabled = true;
        document.getElementById('stopRecord').disabled = false;
    } catch (err) {
        console.error("Error:", err);
        alert("Error accessing microphone: " + err.message);
    }
}

function stopRecording() {
    mediaRecorder.stop();
    document.getElementById('startRecord').disabled = false;
    document.getElementById('stopRecord').disabled = true;
    
    // Stop all tracks in all streams
    mediaRecorder.stream.getTracks().forEach(track => track.stop());
}
</script>
"""

# Initialize session state
if 'logs' not in st.session_state:
    st.session_state.logs = []
if 'transcription' not in st.session_state:
    st.session_state.transcription = ""
if 'conversation' not in st.session_state:
    st.session_state.conversation = []
if 'audio_data' not in st.session_state:
    st.session_state.audio_data = None

def add_log(event_type, source='server'):
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_entry = {
        'timestamp': timestamp,
        'type': event_type,
        'source': source
    }
    st.session_state.logs.append(log_entry)
    return log_entry

class DeepgramAgent:
    def __init__(self, api_key):
        self.client = DeepgramClient(api_key)
        self.functions = {
            'get_time': self.get_time
        }
    
    def get_time(self):
        """Get the current time"""
        current_time = datetime.now().strftime("%H:%M:%S")
        return f"The current time is {current_time}"
    
    def process_audio(self, audio_data):
        try:
            options = PrerecordedOptions(
                model="nova-2",
                smart_format=True,
                utterances=True,
                punctuate=True
            )
            
            response = self.client.listen.prerecorded.v("1").transcribe_file(
                {"buffer": audio_data},
                options
            )
            
            transcript = response.results.channels[0].alternatives[0].transcript
            
            # Check for function calls
            if "what time" in transcript.lower():
                return self.get_time()
            
            return transcript
            
        except Exception as e:
            return f"Error processing audio: {str(e)}"

# Main app
main_tab, docs_tab = st.tabs(["Console", "Docs"])

with main_tab:
    st.markdown('<img src="https://assets-global.website-files.com/61e47fafb12bd56b40022c49/62570b5740e284635275a342_Deepgram%20Logo.png" width="150"/>', unsafe_allow_html=True)
    st.caption("**realtime console**")
    
    with st.sidebar:
        deepgram_api_key = st.text_input(
            "Deepgram API Key",
            type="password",
            placeholder="Enter your API key",
            key="api_key"
        )
        
        if st.button("Connect", type="primary"):
            if deepgram_api_key:
                try:
                    st.session_state.agent = DeepgramAgent(deepgram_api_key)
                    add_log("connection.established")
                    st.success("Connected to Deepgram API")
                except Exception as e:
                    st.error(f"Connection failed: {str(e)}")
                    add_log("connection.failed")
            else:
                st.error("Please enter your API key")

    show_full_events = st.checkbox("Show Full Event Payloads")
    
    # Logs section
    with st.container(height=250):
        st.markdown("### Logs")
        if show_full_events:
            for log in st.session_state.logs:
                st.json(log)
        else:
            for log in st.session_state.logs:
                if log['source'] == 'server':
                    st.write(f"{log['timestamp']} :green[↓ server] {log['type']}")
                else:
                    st.write(f"{log['timestamp']} :blue[↑ client] {log['type']}")

    # Transcription section
    with st.container(height=250):
        st.markdown("### Transcription")
        st.markdown("**conversation**")
        for msg in st.session_state.conversation:
            st.write(msg)

    # Audio recording component
    st.components.v1.html(AUDIO_RECORDER_HTML, height=100)
    
    # JavaScript callback handler for audio data
    st.components.v1.html(
        """
        <script>
        window.addEventListener('message', function(e) {
            if (e.data.type === 'audio_data') {
                window.parent.postMessage({
                    type: 'streamlit:set_session_state',
                    data: { audio_data: e.data.data }
                }, '*');
            }
        });
        </script>
        """,
        height=0,
    )

    # Send Audio button (only enabled when audio is recorded)
    if st.session_state.audio_data:
        if st.button("Send Audio", type="primary"):
            try:
                add_log("audio.processing", "server")
                
                # Convert base64 to binary
                audio_data = st.session_state.audio_data.split(',')[1]
                audio_binary = base64.b64decode(audio_data)
                
                # Process audio
                result = st.session_state.agent.process_audio(audio_binary)
                
                # Add to conversation
                st.session_state.conversation.append(f"User: {result}")
                add_log("transcription.complete", "server")
                
                # Clear audio data
                st.session_state.audio_data = None
                st.experimental_rerun()
                
            except Exception as e:
                st.error(f"Error processing audio: {str(e)}")
                add_log("audio.error", "server")

    # Text message input
    message = st.text_area("Enter your message:", height=100)
    if st.button("Send", type="primary"):
        if message:
            try:
                event = json.loads(message)
                add_log(f"message.{event['type']}", "client")
                st.session_state.conversation.append(f"User: {event.get('content', '')}")
                add_log("message.received", "server")
            except json.JSONDecodeError:
                st.error("Invalid JSON format")
                add_log("message.error", "server")

with docs_tab:
    st.markdown("""
    # Deepgram Agent Documentation
    
    ## Event Formats
    
    ### Text Message
    ```json
    {
        "type": "conversation.item.create",
        "content": "Your message here"
    }
    ```
    
    ### Audio Recording
    1. Click "Start Recording" to begin recording
    2. Click "Stop Recording" when done
    3. Click "Send Audio" to process the recording
    
    ## Available Functions
    - get_time: Returns the current time when asked
    
    ## Examples
    1. Ask for the time:
       - Say "What time is it?"
       - Or send: {"type": "function.call", "name": "get_time"}
    
    2. Regular conversation:
       - Speak naturally or send text messages
    """)