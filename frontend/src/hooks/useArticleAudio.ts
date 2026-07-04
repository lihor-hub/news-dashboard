import { useEffect, useRef, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { toast } from 'sonner';
import { fetchArticleAudioUrl } from '@/api';

export type AudioState = 'idle' | 'loading' | 'playing' | 'paused';

export function useArticleAudio(id: string | undefined) {
  const [audioState, setAudioState] = useState<AudioState>('idle');
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioUrlRef = useRef<string | null>(null);

  const audioMutation = useMutation({
    mutationFn: () => fetchArticleAudioUrl(id!),
    onSuccess: (url) => {
      audioUrlRef.current = url;
      const audio = new Audio(url);
      audioRef.current = audio;
      audio.onended = () => setAudioState('paused');
      audio.onerror = () => {
        toast.error('Audio playback failed');
        setAudioState('idle');
      };
      void audio.play();
      setAudioState('playing');
    },
    onError: () => {
      toast.error('Could not load audio');
      setAudioState('idle');
    },
  });

  useEffect(() => {
    return () => {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
      }
      if (audioUrlRef.current) {
        URL.revokeObjectURL(audioUrlRef.current);
        audioUrlRef.current = null;
      }
    };
  }, []);

  function handleListen() {
    if (audioState === 'loading') return;
    if (audioState === 'playing') {
      audioRef.current?.pause();
      setAudioState('paused');
      return;
    }
    if (audioState === 'paused' && audioRef.current) {
      void audioRef.current.play();
      setAudioState('playing');
      return;
    }
    setAudioState('loading');
    audioMutation.mutate();
  }

  return { audioState, handleListen };
}
