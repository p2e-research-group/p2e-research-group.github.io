(() => {
  const banner = document.querySelector('.hv-banner');
  if (!banner) return;

  const frames = [...banner.querySelectorAll('[data-frame]')];
  const controls = banner.querySelector('.hv-controls');
  const position = banner.querySelector('[data-position]');
  const announcement = banner.querySelector('[data-slide-status]');
  const captions = [
    'Illustrative exterior view of a process plant',
    'Illustrative plant interior with a heat exchanger'
  ];
  if (frames.length < 2 || !controls || !position || !announcement) return;

  let current = 0;
  function move(step) {
    current = (current + step + frames.length) % frames.length;
    frames.forEach((frame, i) => { frame.hidden = i !== current; });
    position.textContent = (current + 1) + ' / ' + frames.length;
    announcement.textContent = captions[current];
  }
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
