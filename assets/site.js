(() => {
  const root = document.documentElement;
  const menu = document.querySelector('.menu');
  const menuButton = document.querySelector('.nav-toggle');
  const header = document.querySelector('.site-header');
  const mobileMenu = window.matchMedia('(max-width: 1080px)');
  const publicationsMenu = menu?.querySelector('.nav-publications');
  const publicationsToggle = publicationsMenu?.querySelector('summary');
  let openedOnHover = false;
  const closePublications = () => {
    if (publicationsMenu) publicationsMenu.open = false;
    openedOnHover = false;
  };
  const syncHeaderOffset = () => {
    if (header) root.style.setProperty('--header-offset', `${Math.ceil(header.getBoundingClientRect().height)}px`);
  };
  syncHeaderOffset();
  if (header && 'ResizeObserver' in window) new ResizeObserver(syncHeaderOffset).observe(header);
  else window.addEventListener('resize', syncHeaderOffset);

  const setMenu = (open, restoreFocus = false) => {
    const wasOpen = menu?.classList.contains('open');
    if (!open) closePublications();
    menu?.classList.toggle('open', open);
    menuButton?.setAttribute('aria-expanded', String(open));
    menuButton?.setAttribute('aria-label', open ? 'Close navigation' : 'Open navigation');
    if (!open && wasOpen && restoreFocus) menuButton?.focus();
  };

  if (menu && menuButton) {
    if (publicationsMenu && publicationsToggle) {
      // Native <details> handles tap, keyboard activation and the no-script path.
      publicationsMenu.addEventListener('pointerenter', (event) => {
        if (!mobileMenu.matches && event.pointerType === 'mouse' && !publicationsMenu.open) {
          publicationsMenu.open = true;
          openedOnHover = true;
        }
      });
      publicationsMenu.addEventListener('pointerleave', () => {
        if (openedOnHover && !publicationsMenu.contains(document.activeElement)) closePublications();
      });
      publicationsToggle.addEventListener('click', (event) => {
        if (openedOnHover && event.detail > 0) event.preventDefault();
        openedOnHover = false;
      });
      publicationsMenu.addEventListener('focusout', (event) => {
        if (event.relatedTarget instanceof Node && !publicationsMenu.contains(event.relatedTarget)) closePublications();
      });
    }
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
      if (event.key !== 'Escape') return;
      if (publicationsMenu?.open) {
        const focusWasInside = publicationsMenu.contains(document.activeElement);
        closePublications();
        if (focusWasInside) publicationsToggle?.focus();
        event.preventDefault();
      } else if (menu.classList.contains('open')) {
        event.preventDefault();
        setMenu(false, true);
      }
    });
    document.addEventListener('click', (event) => {
      if (!(event.target instanceof Node)) return;
      if (header && !header.contains(event.target)) setMenu(false);
      else if (!publicationsMenu?.contains(event.target)) closePublications();
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
