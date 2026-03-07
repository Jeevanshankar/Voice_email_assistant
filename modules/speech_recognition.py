import subprocess
import whisper
import os

# Make ffmpeg available to Whisper internally
os.environ["PATH"] += os.pathsep + r"C:\Users\Krish\Downloads\ffmpeg-2026-02-09-git-9bfa1635ae-full_build\ffmpeg-2026-02-09-git-9bfa1635ae-full_build\bin"

# Hardcoded ffmpeg path for manual conversion
FFMPEG_PATH = r"C:\Users\Krish\Downloads\ffmpeg-2026-02-09-git-9bfa1635ae-full_build\ffmpeg-2026-02-09-git-9bfa1635ae-full_build\bin\ffmpeg.exe"

# Load Whisper model once
model = whisper.load_model("base")

def transcribe_audio(input_path):
    wav_path = "converted.wav"

    # Convert WEBM → WAV
    subprocess.run([
        FFMPEG_PATH, "-y", "-i", input_path, "-ar", "16000", "-ac", "1", wav_path
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # Transcribe using Whisper
    result = model.transcribe(wav_path)

    # Cleanup
    if os.path.exists(wav_path):
        os.remove(wav_path)

    return result["text"]
