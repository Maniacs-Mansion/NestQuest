import "./cards/party-board";
import "./cards/quest-log";
import "./cards/admin";

const FONTS_HREF = "/nestquest-static/nestquest-fonts.css";
if (!document.querySelector('link[data-nq-fonts=""]')) {
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = FONTS_HREF;
  link.dataset.nqFonts = "";
  document.head.appendChild(link);
}
