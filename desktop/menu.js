// Native application menu. Keeps standard edit/view/window roles and adds a
// "Server" item so users can repoint the app at a different ERP backend.
const { app, Menu, shell } = require("electron");

module.exports = function buildMenu({ onChangeServer }) {
  const isMac = process.platform === "darwin";

  const template = [
    ...(isMac ? [{ role: "appMenu" }] : []),
    {
      label: "File",
      submenu: [
        { label: "ERP Server…", click: () => onChangeServer && onChangeServer() },
        { type: "separator" },
        isMac ? { role: "close" } : { role: "quit" },
      ],
    },
    { role: "editMenu" },
    {
      label: "View",
      submenu: [
        { role: "reload" },
        { role: "forceReload" },
        { type: "separator" },
        { role: "resetZoom" },
        { role: "zoomIn" },
        { role: "zoomOut" },
        { type: "separator" },
        { role: "togglefullscreen" },
      ],
    },
    { role: "windowMenu" },
    {
      role: "help",
      submenu: [
        { label: "Documentation", click: () => shell.openExternal("https://ormodex.com/docs") },
        { label: "Contact Support", click: () => shell.openExternal("https://ormodex.com/contact") },
        { type: "separator" },
        { label: `Version ${app.getVersion()}`, enabled: false },
      ],
    },
  ];

  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
};
