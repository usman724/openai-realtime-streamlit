import queue
import sounddevice as sd
import os  # <<-- Add this line
from datetime import datetime

class StreamingAudioRecorder:
    def __init__(self):
        self.audio_queue = queue.Queue()
        self.recording = False
        self.audio_thread = None

    def callback(self, indata, frames, time, status):
        if status:
            print(f"Status: {status}")
        if self.recording:
            self.audio_queue.put(indata.copy().tobytes())

    def start_recording(self):
        self.recording = True
        self.audio_thread = sd.InputStream(
            channels=1,
            samplerate=24000,
            dtype=np.int16,
            callback=self.callback,
            blocksize=2000
        )
        self.audio_thread.start()

    def stop_recording(self):
        if self.audio_thread is not None:
            self.recording = False
            self.audio_thread.stop()
            self.audio_thread.close()
            self.audio_thread = None