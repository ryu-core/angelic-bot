import { useEffect, useRef, useState } from "react";
import { useCapabilities } from "../hooks/useCapabilities.js";

const DEFAULT_VIDEO_SOURCE = "/media/xiel-saturn-clean.mp4";
const DEFAULT_POSTER_SOURCE = "/media/xiel-saturn-poster-clean.jpg";

function clamp(value, minimum = 0, maximum = 1) {
  return Math.min(maximum, Math.max(minimum, value));
}

function phaseForProgress(progress) {
  if (progress <= 0.08) return "approach";
  if (progress < 0.48) return "orbit";
  if (progress < 0.9) return "eclipse";
  return "departure";
}

export default function SaturnScrollScene({
  children,
  poster = DEFAULT_POSTER_SOURCE,
  source = DEFAULT_VIDEO_SOURCE,
}) {
  const rootRef = useRef(null);
  const videoRef = useRef(null);
  const playbackAllowedRef = useRef(false);
  const [videoFailed, setVideoFailed] = useState(false);
  const { isMobile, reducedMotion, saveData } = useCapabilities();
  const staticExperience = isMobile || reducedMotion || saveData || videoFailed;

  useEffect(() => {
    const root = rootRef.current;
    const video = videoRef.current;
    if (!root || !video || staticExperience) return undefined;

    let frameId = 0;
    let intersecting = false;
    let pageVisible = document.visibilityState !== "hidden";
    let observer;

    const renderProgress = () => {
      frameId = 0;
      const bounds = root.getBoundingClientRect();
      const viewportHeight = Math.max(window.innerHeight, 1);
      const scrollDistance = Math.max(bounds.height - viewportHeight, 1);
      const progress = clamp(-bounds.top / scrollDistance);
      const phase = phaseForProgress(progress);

      root.style.setProperty("--saturn-scroll-progress", progress.toFixed(4));
      if (root.dataset.scrollPhase !== phase) root.dataset.scrollPhase = phase;
    };

    const scheduleProgress = () => {
      if (!frameId) frameId = window.requestAnimationFrame(renderProgress);
    };

    const setPlayback = () => {
      const shouldPlay = intersecting && pageVisible;
      playbackAllowedRef.current = shouldPlay;

      if (!shouldPlay) {
        video.pause();
        root.dataset.playback = "paused";
        return;
      }

      const playback = video.play();
      if (playback?.catch) {
        playback.catch(() => {
          root.dataset.playback = "blocked";
        });
      }
    };

    const handleScroll = () => {
      if (intersecting) scheduleProgress();
    };

    const handleResize = () => {
      scheduleProgress();
    };

    const handleVisibility = () => {
      pageVisible = document.visibilityState !== "hidden";
      setPlayback();
    };

    video.pause();
    root.dataset.playback = "paused";

    if ("IntersectionObserver" in window) {
      observer = new IntersectionObserver(
        ([entry]) => {
          intersecting = Boolean(entry?.isIntersecting);
          setPlayback();
          scheduleProgress();
        },
        { rootMargin: "12% 0px", threshold: 0 },
      );
      observer.observe(root);
    } else {
      intersecting = true;
      setPlayback();
      scheduleProgress();
    }

    window.addEventListener("scroll", handleScroll, { passive: true });
    window.addEventListener("resize", handleResize, { passive: true });
    document.addEventListener("visibilitychange", handleVisibility);
    scheduleProgress();

    return () => {
      playbackAllowedRef.current = false;
      observer?.disconnect();
      window.cancelAnimationFrame(frameId);
      window.removeEventListener("scroll", handleScroll);
      window.removeEventListener("resize", handleResize);
      document.removeEventListener("visibilitychange", handleVisibility);
      video.pause();
    };
  }, [staticExperience]);

  return <div
    ref={rootRef}
    className={`saturn-scroll-scene${staticExperience ? " saturn-scroll-scene--static" : ""}`}
    data-scroll-phase="approach"
  >
    <div className="saturn-scroll-scene__stage">
      <div className="saturn-scroll-scene__media" aria-hidden="true">
        {staticExperience
          ? <img
            className="saturn-scroll-scene__poster"
            src={poster}
            alt=""
            loading="eager"
            fetchPriority="high"
          />
          : <video
            ref={videoRef}
            className="saturn-scroll-scene__video"
            src={source}
            poster={poster}
            autoPlay
            loop
            muted
            playsInline
            preload="metadata"
            disablePictureInPicture
            tabIndex="-1"
            onCanPlay={() => {
              rootRef.current?.setAttribute("data-media-ready", "true");
            }}
            onPlaying={() => {
              rootRef.current?.setAttribute("data-playback", "playing");
            }}
            onPlay={() => {
              if (!playbackAllowedRef.current) videoRef.current?.pause();
            }}
            onError={() => setVideoFailed(true)}
          />}
        <div className="saturn-scroll-scene__wash" />
        <div className="saturn-scroll-scene__orbits">
          <i />
          <i />
          <i />
        </div>
      </div>

      <div className="saturn-scroll-scene__content">
        {children}
      </div>

      <div className="saturn-scroll-scene__progress" aria-hidden="true">
        <span>Scroll to orbit</span>
        <i />
      </div>
    </div>
  </div>;
}
