// Runs before the page is drawn: marks that scripts run (so what is revealed on scroll starts hidden only then), and skips the intro loader after the first page of a visit.
(function () {
  var d = document.documentElement;
  d.classList.remove("no-js");
  d.classList.add("js");
  try {
    if (sessionStorage.getItem("seen")) d.classList.add("no-loader");
    sessionStorage.setItem("seen", "1");
  } catch (e) { d.classList.add("no-loader"); }
  if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) d.classList.add("no-loader", "reduced");
})();
