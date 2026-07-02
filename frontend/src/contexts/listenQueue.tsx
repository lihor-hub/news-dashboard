import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { fetchArticleAudioUrl } from '@/api';
import { patchArticleState } from '@/api/workflowApi';
import type { WorkflowArticle } from '@/lib/workflowTypes';
import {
  getMarkDoneOnFinish,
  setMarkDoneOnFinish as persistMarkDoneOnFinish,
} from '@/lib/listenQueueSettings';
import { trackFeature } from '@/lib/analytics';

interface ListenQueueContextValue {
  queue: WorkflowArticle[];
  currentIndex: number;
  current: WorkflowArticle | null;
  isPlaying: boolean;
  isLoading: boolean;
  currentTime: number;
  duration: number;
  markDoneOnFinish: boolean;
  setMarkDoneOnFinish: (value: boolean) => void;
  start: (articles: WorkflowArticle[], startIndex?: number) => void;
  stop: () => void;
  playPause: () => void;
  next: () => void;
  prev: () => void;
  seek: (time: number) => void;
}

const ListenQueueContext = createContext<ListenQueueContextValue | null>(null);

// eslint-disable-next-line react-refresh/only-export-components
export function useListenQueue(): ListenQueueContextValue {
  const ctx = useContext(ListenQueueContext);
  if (!ctx) throw new Error('useListenQueue must be used within a ListenQueueProvider');
  return ctx;
}

export function ListenQueueProvider({ children }: { children: ReactNode }) {
  const [queue, setQueue] = useState<WorkflowArticle[]>([]);
  const [currentIndex, setCurrentIndex] = useState(-1);
  const [isPlaying, setIsPlaying] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [markDoneOnFinish, setMarkDoneOnFinishState] = useState(getMarkDoneOnFinish);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const urlCacheRef = useRef<Map<string, string>>(new Map());
  const queueRef = useRef(queue);
  const indexRef = useRef(currentIndex);
  const markDoneRef = useRef(markDoneOnFinish);

  useEffect(() => {
    queueRef.current = queue;
  }, [queue]);
  useEffect(() => {
    indexRef.current = currentIndex;
  }, [currentIndex]);
  useEffect(() => {
    markDoneRef.current = markDoneOnFinish;
  }, [markDoneOnFinish]);

  const revokeAll = useCallback(() => {
    urlCacheRef.current.forEach((url) => URL.revokeObjectURL(url));
    urlCacheRef.current.clear();
  }, []);

  const loadAudioUrl = useCallback(async (article: WorkflowArticle): Promise<string> => {
    const cached = urlCacheRef.current.get(article.id);
    if (cached) return cached;
    const url = await fetchArticleAudioUrl(article.id);
    urlCacheRef.current.set(article.id, url);
    return url;
  }, []);

  const prefetchNext = useCallback(
    (index: number) => {
      const nextArticle = queueRef.current[index + 1];
      if (!nextArticle) return;
      if (urlCacheRef.current.has(nextArticle.id)) return;
      void loadAudioUrl(nextArticle).catch(() => {
        // Prefetch failures are silent; playback will retry on demand.
      });
    },
    [loadAudioUrl]
  );

  const playIndex = useCallback(
    (index: number) => {
      const article = queueRef.current[index];
      const audio = audioRef.current;
      if (!article || !audio) return;
      indexRef.current = index;
      setIsLoading(true);
      setCurrentIndex(index);
      void loadAudioUrl(article)
        .then((url) => {
          audio.src = url;
          setIsLoading(false);
          return audio.play();
        })
        .then(() => {
          setIsPlaying(true);
          prefetchNext(index);
        })
        .catch(() => {
          setIsLoading(false);
          setIsPlaying(false);
        });
    },
    [loadAudioUrl, prefetchNext]
  );

  const stop = useCallback(() => {
    const audio = audioRef.current;
    if (audio) {
      audio.pause();
      audio.removeAttribute('src');
    }
    revokeAll();
    setQueue([]);
    setCurrentIndex(-1);
    setIsPlaying(false);
    setIsLoading(false);
    setCurrentTime(0);
    setDuration(0);
    if ('mediaSession' in navigator) {
      navigator.mediaSession.metadata = null;
      navigator.mediaSession.playbackState = 'none';
    }
  }, [revokeAll]);

  const start = useCallback(
    (articles: WorkflowArticle[], startIndex = 0) => {
      if (articles.length === 0) return;
      revokeAll();
      queueRef.current = articles;
      setQueue(articles);
      trackFeature('listen_queue_start');
      playIndex(startIndex);
    },
    [playIndex, revokeAll]
  );

  const next = useCallback(() => {
    const nextIndex = indexRef.current + 1;
    if (nextIndex >= queueRef.current.length) {
      stop();
      return;
    }
    playIndex(nextIndex);
  }, [playIndex, stop]);

  const prev = useCallback(() => {
    const prevIndex = indexRef.current - 1;
    if (prevIndex < 0) return;
    playIndex(prevIndex);
  }, [playIndex]);

  const playPause = useCallback(() => {
    const audio = audioRef.current;
    if (!audio || indexRef.current < 0) return;
    if (isPlaying) {
      audio.pause();
      setIsPlaying(false);
    } else {
      void audio.play().then(() => setIsPlaying(true));
    }
  }, [isPlaying]);

  const seek = useCallback((time: number) => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = time;
    setCurrentTime(time);
  }, []);

  const setMarkDoneOnFinish = useCallback((value: boolean) => {
    setMarkDoneOnFinishState(value);
    persistMarkDoneOnFinish(value);
  }, []);

  useEffect(() => {
    const audio = new Audio();
    audioRef.current = audio;
    const cache = urlCacheRef.current;

    const handleEnded = () => {
      const article = queueRef.current[indexRef.current];
      if (article && markDoneRef.current) {
        void patchArticleState(article.id, 'done', article.starred).catch(() => {
          // Best-effort — playback should still advance even if marking done fails.
        });
      }
      next();
    };
    const handleTimeUpdate = () => setCurrentTime(audio.currentTime);
    const handleLoadedMetadata = () => setDuration(audio.duration || 0);
    const handlePlay = () => setIsPlaying(true);
    const handlePause = () => setIsPlaying(false);

    audio.addEventListener('ended', handleEnded);
    audio.addEventListener('timeupdate', handleTimeUpdate);
    audio.addEventListener('loadedmetadata', handleLoadedMetadata);
    audio.addEventListener('play', handlePlay);
    audio.addEventListener('pause', handlePause);

    return () => {
      audio.removeEventListener('ended', handleEnded);
      audio.removeEventListener('timeupdate', handleTimeUpdate);
      audio.removeEventListener('loadedmetadata', handleLoadedMetadata);
      audio.removeEventListener('play', handlePlay);
      audio.removeEventListener('pause', handlePause);
      audio.pause();
      cache.forEach((url) => URL.revokeObjectURL(url));
      cache.clear();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!('mediaSession' in navigator)) return;
    const article = queue[currentIndex];
    if (!article) return;
    navigator.mediaSession.metadata = new MediaMetadata({
      title: article.title,
      artist: article.sourceName,
    });
    navigator.mediaSession.playbackState = isPlaying ? 'playing' : 'paused';
    navigator.mediaSession.setActionHandler('play', playPause);
    navigator.mediaSession.setActionHandler('pause', playPause);
    navigator.mediaSession.setActionHandler('previoustrack', prev);
    navigator.mediaSession.setActionHandler('nexttrack', next);
    navigator.mediaSession.setActionHandler('seekto', (details) => {
      if (typeof details.seekTime === 'number') seek(details.seekTime);
    });
  }, [queue, currentIndex, isPlaying, playPause, prev, next, seek]);

  const value: ListenQueueContextValue = {
    queue,
    currentIndex,
    current: currentIndex >= 0 ? (queue[currentIndex] ?? null) : null,
    isPlaying,
    isLoading,
    currentTime,
    duration,
    markDoneOnFinish,
    setMarkDoneOnFinish,
    start,
    stop,
    playPause,
    next,
    prev,
    seek,
  };

  return <ListenQueueContext.Provider value={value}>{children}</ListenQueueContext.Provider>;
}
