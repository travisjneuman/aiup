"use strict";

const copyButton = document.querySelector("[data-copy-target]");
const copyStatus = document.querySelector("#copy-status");

async function copyText(element) {
  const text = element.textContent.trim();
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const selection = window.getSelection();
  const range = document.createRange();
  range.selectNodeContents(element);
  selection.removeAllRanges();
  selection.addRange(range);
  const copied = document.execCommand("copy");
  selection.removeAllRanges();
  if (!copied) {
    throw new Error("Copy command was not accepted");
  }
}

if (copyButton && copyStatus) {
  copyButton.hidden = false;
  copyButton.addEventListener("click", async () => {
    const target = document.getElementById(copyButton.dataset.copyTarget);
    if (!target) return;

    try {
      await copyText(target);
      copyButton.textContent = "Copied";
      copyStatus.textContent = "Install command copied to the clipboard.";
    } catch {
      copyButton.textContent = "Copy unavailable";
      copyStatus.textContent = "Select the command and copy it manually.";
    }

    window.setTimeout(() => {
      copyButton.textContent = "Copy command";
      copyStatus.textContent = "";
    }, 4000);
  });
}

const animationButton = document.querySelector("#animation-toggle");
const animationImage = document.querySelector("#motion-demo-image");
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

if (animationButton && animationImage) {
  const reducedSource = document.querySelector("#motion-demo source");
  let isPlaying = !reducedMotion.matches;

  function showMotion() {
    if (reducedSource) reducedSource.srcset = animationImage.dataset.motionSrc;
    animationImage.src = animationImage.dataset.motionSrc;
    animationButton.textContent = "Pause animation";
    animationButton.setAttribute("aria-pressed", "false");
    isPlaying = true;
  }

  function showPoster() {
    if (reducedSource) reducedSource.srcset = animationImage.dataset.posterSrc;
    animationImage.src = animationImage.dataset.posterSrc;
    animationButton.textContent = "Play animation";
    animationButton.setAttribute("aria-pressed", "true");
    isPlaying = false;
  }

  if (reducedMotion.matches) showPoster();
  animationButton.hidden = false;
  animationButton.addEventListener("click", () => {
    if (isPlaying) showPoster();
    else showMotion();
  });
}
