// Sticky-nav border, and clips that only play while on screen.
const nav = document.querySelector('.nav')
addEventListener('scroll', () => nav.classList.toggle('stuck', scrollY > 8), { passive: true })

const io = new IntersectionObserver((entries) => {
  for (const e of entries) {
    const v = e.target.querySelector?.('video')
    if (v && !matchMedia('(prefers-reduced-motion: reduce)').matches) e.isIntersecting ? v.play().catch(() => {}) : v.pause()
  }
}, { threshold: 0.25 })
document.querySelectorAll('.frame').forEach((el) => io.observe(el))
