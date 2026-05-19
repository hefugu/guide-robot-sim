import {
  cellToLabel,
  drawScene,
  getCellFromMouseEvent,
  isSameCell,
  isWallCell,
  loadAppState,
  loadImageFromSrc,
  saveAppState,
} from "./shared.js";

const canvas = document.getElementById("clientMapCanvas");
const ctx = canvas.getContext("2d");

const elements = {
  status: document.getElementById("clientStatus"),
  toolLabel: document.getElementById("clientToolLabel"),

  toolUser: document.getElementById("toolUser"),
  toolGoal: document.getElementById("toolGoal"),
  toolErase: document.getElementById("toolErase"),
  btnGuideRequest: document.getElementById("btnGuideRequest"),

  userPositionLabel: document.getElementById("userPositionLabel"),
  goalPositionLabel: document.getElementById("goalPositionLabel"),
  robotPositionLabel: document.getElementById("robotPositionLabel"),

  logOutput: document.getElementById("clientLogOutput"),
};

let appState = loadAppState();
let mapImage = null;
let currentImageDataUrl = null;
let currentTool = "user";

function log(message) {
  const time = new Date().toLocaleTimeString();
  elements.logOutput.value += `[${time}] ${message}\n`;
  elements.logOutput.scrollTop = elements.logOutput.scrollHeight;
}

async function ensureMapImage() {
  const imageDataUrl = appState.map.imageDataUrl;

  if (!imageDataUrl) {
    mapImage = null;
    currentImageDataUrl = null;
    return;
  }

  if (currentImageDataUrl === imageDataUrl && mapImage) {
    return;
  }

  mapImage = await loadImageFromSrc(imageDataUrl);
  currentImageDataUrl = imageDataUrl;
}

function saveAndRender() {
  appState = saveAppState(appState);
  render();
}

function getToolLabel(tool) {
  const labels = {
    user: "利用者位置",
    goal: "目的地",
    erase: "消去",
  };

  return labels[tool] ?? tool;
}

function setTool(tool) {
  currentTool = tool;

  elements.toolUser.classList.toggle("active", tool === "user");
  elements.toolGoal.classList.toggle("active", tool === "goal");
  elements.toolErase.classList.toggle("active", tool === "erase");

  elements.toolLabel.textContent = getToolLabel(tool);
  log(`ツール変更: ${getToolLabel(tool)}`);
}

function updateInfo() {
  elements.status.textContent = appState.robot.status;
  elements.userPositionLabel.textContent = cellToLabel(appState.user.position);
  elements.goalPositionLabel.textContent = cellToLabel(appState.goal.position);
  elements.robotPositionLabel.textContent = cellToLabel(appState.robot.position);
}

async function render() {
  await ensureMapImage();

  drawScene({
    canvas,
    ctx,
    state: appState,
    image: mapImage,

    // 子機は利用者に必要な情報だけ表示する。
    // 経路・障害物・待機位置は管理情報なので隠す。
    showPaths: false,
    showHome: false,
    showRobot: true,
    showUser: true,
    showGoal: true,
    showObstacles: false,
  });

  updateInfo();
}

function eraseAt(cell) {
  if (isSameCell(appState.user.position, cell)) {
    appState.user.position = null;
    log(`利用者位置を削除: (${cell.x}, ${cell.y})`);
  }

  if (isSameCell(appState.goal.position, cell)) {
    appState.goal.position = null;
    log(`目的地を削除: (${cell.x}, ${cell.y})`);
  }
}

function clearRequestAndPaths() {
  appState.paths.toUser = [];
  appState.paths.toGoal = [];
  appState.request.active = false;

  if (
    appState.robot.status !== "GO_TO_USER" &&
    appState.robot.status !== "GUIDING_TO_GOAL" &&
    appState.robot.status !== "STOPPED_BY_OBSTACLE" &&
    appState.robot.status !== "ARRIVED"
  ) {
    appState.robot.status = "WAITING";
  }
}

function handleCanvasClick(event) {
  if (!mapImage) {
    log("親機でマップを読み込んでください");
    return;
  }

  const cell = getCellFromMouseEvent(canvas, event, mapImage, appState);

  if (!cell) {
    return;
  }

  if (currentTool !== "erase" && isWallCell(appState, cell)) {
    log(`壁マスには配置できません: (${cell.x}, ${cell.y})`);
    return;
  }

  if (currentTool === "user") {
    appState.user.position = { ...cell };
    log(`利用者位置を設定: (${cell.x}, ${cell.y})`);
    clearRequestAndPaths();
  }

  if (currentTool === "goal") {
    appState.goal.position = { ...cell };
    log(`目的地を設定: (${cell.x}, ${cell.y})`);
    clearRequestAndPaths();
  }

  if (currentTool === "erase") {
    eraseAt(cell);
    clearRequestAndPaths();
  }

  saveAndRender();
}

function handleGuideRequest() {
  if (!appState.map.imageLoaded) {
    log("案内開始不可: 親機でマップを読み込んでください");
    return;
  }

  if (!appState.robot.home) {
    log("案内開始不可: 親機で待機位置を設定してください");
    return;
  }

  if (!appState.user.position) {
    log("案内開始不可: 利用者位置が未設定です");
    return;
  }

  if (!appState.goal.position) {
    log("案内開始不可: 目的地が未設定です");
    return;
  }

  appState.request.active = true;
  appState.request.id = Date.now();
  appState.robot.status = "REQUEST_RECEIVED";

  appState = saveAppState(appState);

  log("案内開始を送信しました");
  render();
}

async function syncFromStorage() {
  const latest = loadAppState();

  if (latest.updatedAt === appState.updatedAt) {
    return;
  }

  appState = latest;
  await render();
}

function bindEvents() {
  elements.toolUser.addEventListener("click", () => setTool("user"));
  elements.toolGoal.addEventListener("click", () => setTool("goal"));
  elements.toolErase.addEventListener("click", () => setTool("erase"));
  elements.btnGuideRequest.addEventListener("click", handleGuideRequest);

  canvas.addEventListener("click", handleCanvasClick);

  window.addEventListener("storage", () => {
    syncFromStorage();
  });

  setInterval(syncFromStorage, 300);
}

function initCanvas() {
  canvas.width = 1000;
  canvas.height = 720;
}

async function init() {
  bindEvents();
  initCanvas();

  setTool("user");
  await render();

  log("子機画面を起動しました");
}

init();