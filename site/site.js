"use strict";

const animationButton = document.querySelector("#animation-toggle");
const animationImage = document.querySelector("#primary-tui-image");
const reducedSource = document.querySelector("#primary-tui-reduced");
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

if (animationButton && animationImage && reducedSource) {
  let isPlaying = !reducedMotion.matches;

  function setPlaying(playing) {
    const source = playing ? animationImage.dataset.motionSrc : animationImage.dataset.posterSrc;
    reducedSource.srcset = source;
    animationImage.src = source;
    animationButton.textContent = playing ? "Pause animation" : "Play animation";
    animationButton.setAttribute("aria-label", `${playing ? "Pause" : "Play"} aiup TUI animation`);
    animationButton.setAttribute("aria-pressed", String(!playing));
    animationButton.dataset.state = playing ? "playing" : "paused";
    isPlaying = playing;
  }

  setPlaying(isPlaying);
  animationButton.hidden = false;
  animationButton.addEventListener("click", () => setPlaying(!isPlaying));

  const followMotionPreference = (event) => setPlaying(!event.matches);
  if (typeof reducedMotion.addEventListener === "function") {
    reducedMotion.addEventListener("change", followMotionPreference);
  } else {
    reducedMotion.addListener(followMotionPreference);
  }
}
