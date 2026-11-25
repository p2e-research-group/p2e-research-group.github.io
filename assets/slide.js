(() => {
  const banner = document.querySelector('.hv-banner');
  if (!banner) return;

  const frames = [...banner.querySelectorAll('[data-frame]')];
  const controls = banner.querySelector('.hv-controls');
  const position = banner.querySelector('[data-position]');
  const announcement = banner.querySelector('[data-slide-status]');
  const captions = [
    'Image 1 of 2: Process plant',
    'Image 2 of 2: A digital twin of an integrated process plant'
  ];
  if (frames.length < 2 || !controls || !position || !announcement) return;

  let current = 0;
  function move(step) {
    current = (current + step + frames.length) % frames.length;
    frames.forEach((frame, i) => { frame.hidden = i !== current; });
    position.textContent = (current + 1) + ' / ' + frames.length;
    announcement.textContent = captions[current];
  }
  position.hidden = false;
  controls.hidden = false;
  controls.querySelectorAll('[data-step]').forEach((button) => {
    button.addEventListener('click', () => move(Number(button.dataset.step)));
  });
  banner.addEventListener('keydown', (event) => {
    if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') {
      event.preventDefault();
      move(event.key === 'ArrowLeft' ? -1 : 1);
    }
  });
})();
