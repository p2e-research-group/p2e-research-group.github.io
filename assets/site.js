(() => {
  const root = document.documentElement;
  const menu = document.querySelector('.menu');
  const menuButton = document.querySelector('.nav-toggle');
  const header = document.querySelector('.site-header');
  const mobileMenu = window.matchMedia('(max-width: 1080px)');
  const syncHeaderOffset = () => {
    if (header) root.style.setProperty('--header-offset', `${Math.ceil(header.getBoundingClientRect().height)}px`);
  };
  syncHeaderOffset();
  if (header && 'ResizeObserver' in window) new ResizeObserver(syncHeaderOffset).observe(header);
  else window.addEventListener('resize', syncHeaderOffset);

  const setMenu = (open, restoreFocus = false) => {
    const wasOpen = menu?.classList.contains('open');
    menu?.classList.toggle('open', open);
    menuButton?.setAttribute('aria-expanded', String(open));
    menuButton?.setAttribute('aria-label', open ? 'Close navigation' : 'Open navigation');
    if (!open && wasOpen && restoreFocus) menuButton?.focus();
  };

  if (menu && menuButton) {
    let focusWasInMenu = false;
    document.addEventListener('focusin', (event) => {
      focusWasInMenu = event.target instanceof Node && menu.contains(event.target);
    });
    menuButton.addEventListener('click', () => {
      const open = !menu.classList.contains('open');
      setMenu(open);
      if (open) menu.querySelector('a')?.focus();
    });
    menu.querySelectorAll('a').forEach((link) => link.addEventListener('click', () => setMenu(false)));
    root.classList.add('nav-ready');
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && menu.classList.contains('open')) {
        event.preventDefault();
        setMenu(false, true);
      }
    });
    document.addEventListener('click', (event) => {
      if (event.target instanceof Node && header && !header.contains(event.target)) setMenu(false);
    });
    header?.addEventListener('focusout', (event) => {
      if (event.relatedTarget instanceof Node && !header.contains(event.relatedTarget)) setMenu(false);
    });
    const onBreakpointChange = () => {
      const focusedLinkWillBeHidden = mobileMenu.matches && (focusWasInMenu || menu.contains(document.activeElement));
      setMenu(false);
      if (focusedLinkWillBeHidden) menuButton.focus();
    };
    if (mobileMenu.addEventListener) mobileMenu.addEventListener('change', onBreakpointChange);
    else mobileMenu.addListener(onBreakpointChange);
  }

  root.classList.remove('reveal-ready');
  document.querySelectorAll('.reveal').forEach((element) => element.classList.add('visible'));

  const filterButtons = [...document.querySelectorAll('[data-publication-filter]')];
  const publications = [...document.querySelectorAll('[data-publication-category]')];
  const filterStatus = document.getElementById('publication-filter-status');
  const updateFilterStatus = () => {
    if (!filterStatus) return;
    const visible = publications.filter((publication) => !publication.hidden).length;
    filterStatus.textContent = `Showing ${visible} of ${publications.length} publications`;
  };
  filterButtons.forEach((button) => {
    button.addEventListener('click', () => {
      const category = button.dataset.publicationFilter || 'all';
      filterButtons.forEach((item) => item.setAttribute('aria-pressed', String(item === button)));
      publications.forEach((publication) => {
        publication.hidden = category !== 'all' && publication.dataset.publicationCategory !== category;
      });
      updateFilterStatus();
    });
  });
  if (filterButtons.length && publications.length) {
    root.classList.add('publication-filter-ready');
    updateFilterStatus();
  }
})();
