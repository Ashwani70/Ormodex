// Native application menu. Keeps standard edit/view/window roles and adds
// "Server" + "Check for Updates" + "Print" so users can repoint the app at a
// different ERP backend, manually trigger an update check, or print the
// current screen without leaving the keyboard.
const { app, Menu, shell, BrowserWindow } = require("electron");

module.exports = function buildMenu({ onChangeServer, onCheckForUpdates }) {
  const isMac = process.platform === "darwin";

  const template = [
    ...(isMac ? [{ role: "appMenu" }] : []),
    {
      label: "File",
      submenu: [
        { label: "ERP Server…", click: () => onChangeServer && onChangeServer() },
        { type: "separator" },
        {
          label: "Print…",
          accelerator: "CmdOrCtrl+P",
          click: (_item, win) => (win || BrowserWindow.getFocusedWindow())?.webContents.print({ printBackground: true }),
        },
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
        {
          label: "Check for Updates…",
          click: () => onCheckForUpdates && onCheckForUpdates(),
        },
        { type: "separator" },
        { label: "Documentation", click: () => shell.openExternal("https://ormodex.com/docs") },
        { label: "Contact Support", click: () => shell.openExternal("https://ormodex.com/contact") },
        { type: "separator" },
        { label: `Version ${app.getVersion()}`, enabled: false },
      ],
    },
  ];

  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
};
