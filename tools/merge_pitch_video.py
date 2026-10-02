#!/usr/bin/env python3
"""
Pitch Video Merger Utility
Merges an input video demonstration with custom voiceover and background music.
Configurable via command-line arguments or environment variables.
"""
import os
import sys
import argparse
from dotenv import load_dotenv
from moviepy import VideoFileClip, AudioFileClip
from moviepy.audio.AudioClip import CompositeAudioClip

load_dotenv()


def merge_pitch_video(video_path: str, voiceover_path: str, bgm_path: str = None, output_path: str = "final_pitch_submission.mp4", bgm_volume: float = 0.12):
    if not os.path.exists(video_path):
        print(f"Error: Input video not found at '{video_path}'")
        sys.exit(1)
        
    if not os.path.exists(voiceover_path):
        print(f"Error: Voiceover audio not found at '{voiceover_path}'")
        sys.exit(1)
        
    print(f"Loading video from: {video_path}")
    print(f"Loading voiceover from: {voiceover_path}")
    video_clip = VideoFileClip(video_path)
    voice_clip = AudioFileClip(voiceover_path)
    
    # Calculate duration
    duration = voice_clip.duration
    video_clip = video_clip.subclipped(0, min(duration, video_clip.duration))
    
    if bgm_path and os.path.exists(bgm_path):
        print(f"Mixing background music from: {bgm_path} (volume={bgm_volume})...")
        bg_clip = AudioFileClip(bgm_path)
        
        # Loop using MoviePy AudioLoop if available
        try:
            from moviepy.audio.fx.AudioLoop import AudioLoop
            bg_clip_looped = bg_clip.with_effects([AudioLoop(duration=duration)])
        except Exception as e:
            print(f"Warning: AudioLoop failed ({e}), using raw clip.")
            bg_clip_looped = bg_clip
            
        bg_clip_ducked = bg_clip_looped.with_volume_scaled(bgm_volume)
        final_audio = CompositeAudioClip([voice_clip, bg_clip_ducked])
    else:
        print("BGM track not provided or not found, using voiceover only.")
        bg_clip = None
        final_audio = voice_clip
        
    print(f"Stitching audio to video track and exporting to '{output_path}'...")
    final_video = video_clip.with_audio(final_audio)
    
    final_video.write_videofile(
        output_path,
        fps=24,
        codec="libx264",
        audio_codec="aac",
        temp_audiofile="temp-pitch-audio.m4a",
        remove_temp=True
    )
    
    # Clean up resources
    video_clip.close()
    voice_clip.close()
    if bg_clip is not None:
        bg_clip.close()
    print(f"Successfully exported final pitch submission video to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Merge video demo with voiceover audio and optional background music.")
    parser.add_argument("--video", "-v", default=os.getenv("PITCH_VIDEO_PATH"), help="Path to source MP4 video file (or env: PITCH_VIDEO_PATH)")
    parser.add_argument("--voiceover", "-a", default=os.getenv("PITCH_VOICEOVER_PATH"), help="Path to voiceover MP3/WAV file (or env: PITCH_VOICEOVER_PATH)")
    parser.add_argument("--bgm", "-b", default=os.getenv("PITCH_BGM_PATH", "static/music/ambient_space.mp3"), help="Path to background music MP3 (default: static/music/ambient_space.mp3, or env: PITCH_BGM_PATH)")
    parser.add_argument("--output", "-o", default=os.getenv("PITCH_OUTPUT_PATH", "final_pitch_submission.mp4"), help="Destination path for final exported MP4 (default: final_pitch_submission.mp4)")
    parser.add_argument("--bgm-volume", type=float, default=float(os.getenv("PITCH_BGM_VOLUME", "0.12")), help="Volume multiplier for BGM (default: 0.12)")

    args = parser.parse_args()

    if not args.video:
        parser.print_help()
        print("\nError: Please provide --video <path_to_video.mp4> or set PITCH_VIDEO_PATH environment variable.")
        sys.exit(1)
        
    if not args.voiceover:
        parser.print_help()
        print("\nError: Please provide --voiceover <path_to_voiceover.mp3> or set PITCH_VOICEOVER_PATH environment variable.")
        sys.exit(1)

    merge_pitch_video(
        video_path=args.video,
        voiceover_path=args.voiceover,
        bgm_path=args.bgm,
        output_path=args.output,
        bgm_volume=args.bgm_volume
    )


if __name__ == "__main__":
    main()
