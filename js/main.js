const canvas = document.getElementById("mapCanvas");
const ctx = canvas.getContext("2d");

const elements = {
  mapFile: document.getElementById("mapFile"),
  thresholdInput: document.getElementById("thresholdInput"),
  thresholdValue: document.getElementById("thresholdValue"),
  gridColsInput: document.getElementById("gridColsInput"),
  gridRowsInput: document.getElementById("gridRowsInput"),
  cellSizeInput: document.getElementById("cellSizeInput"),
  btnGenerateGrid: document.getElementById("btnGenerateGrid"),

  btnParentMode: document.getElementById("btnParentMode"),
  btnClientMode: document.getElementById("btnClientMode"),
  parentPanel: document.getElementById("parentPanel"),
  clientPanel: document.getElementById("clientPanel"),
  modeLabel: document.getElementById("modeLabel"),

  toolHome: document.getElementById("toolHome"),
  toolObstacle: document.getElementById("toolObstacle"),
  toolEraseParent: document.getElementById("toolEraseParent"),
  directionSelect: document.getElementById("directionSelect"),

  toolUser: document.getElementById("toolUser"),
  toolGoal: document.getElementById("toolGoal"),
  toolEraseClient: document.getElementById("toolEraseClient"),
  btnGuideRequest: document.getElementById("btnGuideRequest"),

  btnResetAll: document.getElementById("btnResetAll"),
  btnClearLog: document.getElementById("btnClearLog"),

  statusLabel: document.getElementById("statusLabel"),
  toolLabel: document.getElementById("toolLabel"),
  logOutput: document.getElementById("logOutput"),
  stateOutput: document.getElementById("stateOutput"),
};

const CELL_TYPES = {
  FREE: 0,
  WALL: 1,
};

const state = {
  map: {
    image: null,
    imageLoaded: false,
    grid: [],
    cols: 50,
    rows: 50,
    threshold: 180,
    cellSizeCm: 25,
  },

  ui: {
    mode: "parent",
    tool: "home",
  },

  robot: {
    home: null,
    position: null,
    direction: "E",
    status: "WAITING",
  },

  user: {
    position: null,
  },

  goal: {
    position: null,
  },

  obstacles: [],

  paths: {
    toUser: [],
    toGoal: [],
  }
};

function log(message) {
  const time = new Date().toLocaleTimeString();
  elements.logOutput.value += `[${time}] ${message}\n`;
  elements.logOutput.scrollTop = elements.logOutput.scrollHeight;
}

function updateStateOutput() {
  const view = {
    map: {
      cols: state.map.cols,
      rows: state.map.rows,
      threshold: state.map.threshold,
      cellSizeCm: state.map.cellSizeCm,
      imageLoaded: state.map.imageLoaded,
    },
    ui: state.ui,
    robot: state.robot,
    user: state.user,
    goal: state.goal,
    obstacles: state.obstacles,
  };

  elements.statusLabel.textContent = state.robot.status;
  elements.modeLabel.textContent = state.ui.mode === "parent" ? "親機" : "子機";
  elements.toolLabel.textContent = getToolLabel(state.ui.tool);
  elements.stateOutput.textContent = JSON.stringify(view, null, 2);
}

function getToolLabel(tool) {
  const labels = {
    home: "待機位置",
    obstacle: "障害物",
    user: "利用者位置",
    goal: "目的地",
    erase: "消去",
  };

  return labels[tool] ?? tool;
}

function setMode(mode) {
  state.ui.mode = mode;

  const isParent = mode === "parent";

  elements.btnParentMode.classList.toggle("active", isParent);
  elements.btnClientMode.classList.toggle("active", !isParent);

  elements.parentPanel.classList.toggle("hidden", !isParent);
  elements.clientPanel.classList.toggle("hidden", isParent);

  if (isParent) {
    setTool("home");
  } else {
    setTool("user");
  }

  log(`モード変更: ${isParent ? "親機" : "子機"}`);
  draw();
  updateStateOutput();
}

function setTool(tool) {
  state.ui.tool = tool;

  const toolButtons = [
    elements.toolHome,
    elements.toolObstacle,
    elements.toolEraseParent,
    elements.toolUser,
    elements.toolGoal,
    elements.toolEraseClient,
  ];

  for (const button of toolButtons) {
    button.classList.remove("active");
  }

  if (tool === "home") elements.toolHome.classList.add("active");
  if (tool === "obstacle") elements.toolObstacle.classList.add("active");
  if (tool === "user") elements.toolUser.classList.add("active");
  if (tool === "goal") elements.toolGoal.classList.add("active");
  if (tool === "erase") {
    elements.toolEraseParent.classList.add("active");
    elements.toolEraseClient.classList.add("active");
  }

  log(`ツール変更: ${getToolLabel(tool)}`);
  updateStateOutput();
}

function loadImageFromFile(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const image = new Image();

    image.onload = () => {
      URL.revokeObjectURL(url);
      resolve(image);
    };

    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("画像の読み込みに失敗しました"));
    };

    image.src = url;
  });
}

function resizeCanvasToImage() {
  canvas.width = 1000;
  canvas.height = 720;
}

function getMapLayout() {
  if (!state.map.imageLoaded || !state.map.image) {
    return {
      scale: 1,
      ox: 0,
      oy: 0,
      drawW: canvas.width,
      drawH: canvas.height,
    };
  }

  const image = state.map.image;

  const scale = Math.min(
    canvas.width / image.width,
    canvas.height / image.height
  );

  const drawW = image.width * scale;
  const drawH = image.height * scale;

  const ox = (canvas.width - drawW) / 2;
  const oy = (canvas.height - drawH) / 2;

  return { scale, ox, oy, drawW, drawH };
}

function createEmptyGrid(cols, rows) {
  return Array.from({ length: rows }, () => {
    return Array.from({ length: cols }, () => CELL_TYPES.FREE);
  });
}

function generateGridFromImage() {
  if (!state.map.imageLoaded || !state.map.image) {
    log("マップ画像が未読み込みです");
    return;
  }

  const image = state.map.image;

  const cols = Number(elements.gridColsInput.value);
  const threshold = Number(elements.thresholdInput.value);
  const cellSizeCm = Number(elements.cellSizeInput.value);

  if (!Number.isFinite(cols) || cols <= 0) {
    log("グリッド列数が不正です");
    return;
  }

  // evac-sim寄せ：画像ピクセル上で正方形セルにする
  const cellSizePx = image.width / cols;
  const rows = Math.max(1, Math.floor(image.height / cellSizePx));

  elements.gridRowsInput.value = String(rows);

  state.map.cols = cols;
  state.map.rows = rows;
  state.map.threshold = threshold;
  state.map.cellSizeCm = cellSizeCm;

  const offscreen = document.createElement("canvas");
  offscreen.width = image.width;
  offscreen.height = image.height;

  const offCtx = offscreen.getContext("2d");
  offCtx.drawImage(image, 0, 0);

  const imageData = offCtx.getImageData(0, 0, image.width, image.height);
  const grid = createEmptyGrid(cols, rows);

  for (let gy = 0; gy < rows; gy++) {
    for (let gx = 0; gx < cols; gx++) {
      const startX = Math.floor(gx * cellSizePx);
      const startY = Math.floor(gy * cellSizePx);
      const endX = Math.min(image.width, Math.floor((gx + 1) * cellSizePx));
      const endY = Math.min(image.height, Math.floor((gy + 1) * cellSizePx));

      let darkCount = 0;
      let totalCount = 0;

      for (let y = startY; y < endY; y++) {
        for (let x = startX; x < endX; x++) {
          const index = (y * image.width + x) * 4;
          const r = imageData.data[index];
          const g = imageData.data[index + 1];
          const b = imageData.data[index + 2];

          const brightness = (r + g + b) / 3;

          if (brightness < threshold) {
            darkCount++;
          }

          totalCount++;
        }
      }

      const darkRatio = totalCount > 0 ? darkCount / totalCount : 0;
      grid[gy][gx] = darkRatio >= 0.3 ? CELL_TYPES.WALL : CELL_TYPES.FREE;
    }
  }

  state.map.grid = grid;

  log(`マップ生成完了: ${cols} x ${rows}, 1マス=${cellSizeCm}cm`);
  draw();
  updateStateOutput();
}

function getCellFromMouseEvent(event) {
  if (!state.map.imageLoaded || !state.map.image) {
    return null;
  }

  const rect = canvas.getBoundingClientRect();

  const x = event.clientX - rect.left;
  const y = event.clientY - rect.top;

  const scaleX = canvas.width / rect.width;
  const scaleY = canvas.height / rect.height;

  const canvasX = x * scaleX;
  const canvasY = y * scaleY;

  const layout = getMapLayout();

  const imageX = (canvasX - layout.ox) / layout.scale;
  const imageY = (canvasY - layout.oy) / layout.scale;

  if (
    imageX < 0 ||
    imageY < 0 ||
    imageX >= state.map.image.width ||
    imageY >= state.map.image.height
  ) {
    return null;
  }

  const cellSizePx = state.map.image.width / state.map.cols;

  const gx = Math.floor(imageX / cellSizePx);
  const gy = Math.floor(imageY / cellSizePx);

  if (
    gx < 0 ||
    gy < 0 ||
    gx >= state.map.cols ||
    gy >= state.map.rows
  ) {
    return null;
  }

  return { x: gx, y: gy };
}

function isSameCell(a, b) {
  return a && b && a.x === b.x && a.y === b.y;
}

function removeObstacleAt(cell) {
  state.obstacles = state.obstacles.filter((obstacle) => {
    return !isSameCell(obstacle, cell);
  });
}

function eraseAt(cell) {
  if (isSameCell(state.robot.home, cell)) {
    state.robot.home = null;
    state.robot.position = null;
    log(`待機位置を削除: (${cell.x}, ${cell.y})`);
  }

  if (isSameCell(state.user.position, cell)) {
    state.user.position = null;
    log(`利用者位置を削除: (${cell.x}, ${cell.y})`);
  }

  if (isSameCell(state.goal.position, cell)) {
    state.goal.position = null;
    log(`目的地を削除: (${cell.x}, ${cell.y})`);
  }

  const beforeCount = state.obstacles.length;
  removeObstacleAt(cell);

  if (state.obstacles.length !== beforeCount) {
    log(`障害物を削除: (${cell.x}, ${cell.y})`);
  }
}

function isWallCell(cell) {
  if (!state.map.grid.length) return false;
  return state.map.grid[cell.y]?.[cell.x] === CELL_TYPES.WALL;
}

function isObstacleCell(cell) {
  return state.obstacles.some((obstacle) => {
    return isSameCell(obstacle, cell);
  });
}

function isBlockedCell(cell) {
  if (
    cell.x < 0 ||
    cell.y < 0 ||
    cell.x >= state.map.cols ||
    cell.y >= state.map.rows
  ) {
    return true;
  }

  if (isWallCell(cell)) {
    return true;
  }

  if (isObstacleCell(cell)) {
    return true;
  }

  return false;
}

function findPathBfs(start, goal) {
  if (!start || !goal) {
    return [];
  }

  const queue = [];
  const visited = new Set();
  const parent = new Map();

  const startKey = cellKey(start);
  const goalKey = cellKey(goal);

  queue.push(start);
  visited.add(startKey);

  const directions = [
    { x: 0, y: -1 },
    { x: 1, y: 0 },
    { x: 0, y: 1 },
    { x: -1, y: 0 },
  ];

  while (queue.length > 0) {
    const current = queue.shift();
    const currentKey = cellKey(current);

    if (currentKey === goalKey) {
      return reconstructPath(parent, start, goal);
    }

    for (const direction of directions) {
      const next = {
        x: current.x + direction.x,
        y: current.y + direction.y,
      };

      const nextKey = cellKey(next);

      if (visited.has(nextKey)) {
        continue;
      }

      if (isBlockedCell(next)) {
        continue;
      }

      visited.add(nextKey);
      parent.set(nextKey, current);
      queue.push(next);
    }
  }

  return [];
}

function cellKey(cell) {
  return `${cell.x},${cell.y}`;
}

function reconstructPath(parent, start, goal) {
  const path = [];
  let current = { ...goal };

  while (!isSameCell(current, start)) {
    path.push(current);

    const currentKey = cellKey(current);
    const previous = parent.get(currentKey);

    if (!previous) {
      return [];
    }

    current = previous;
  }

  path.push(start);
  path.reverse();

  return path;
}

function drawPaths() {
  drawPath(state.paths.toUser, "rgba(0, 174, 255, 0.75)");
  drawPath(state.paths.toGoal, "rgba(255, 214, 102, 0.85)");
}

function drawPath(path, color) {
  if (!path || path.length === 0) {
    return;
  }

  if (!state.map.imageLoaded || !state.map.image) {
    return;
  }

  const layout = getMapLayout();
  const cellSizePx = state.map.image.width / state.map.cols;

  ctx.save();
  ctx.translate(layout.ox, layout.oy);
  ctx.scale(layout.scale, layout.scale);

  ctx.fillStyle = color;

  for (const cell of path) {
    ctx.fillRect(
      cell.x * cellSizePx,
      cell.y * cellSizePx,
      cellSizePx,
      cellSizePx
    );
  }

  ctx.restore();
}

function calculateGuidePaths() {
  if (!state.robot.home) {
    log("経路探索不可: 待機位置が未設定です");
    return false;
  }

  if (!state.user.position) {
    log("経路探索不可: 利用者位置が未設定です");
    return false;
  }

  if (!state.goal.position) {
    log("経路探索不可: 目的地が未設定です");
    return false;
  }

  const pathToUser = findPathBfs(state.robot.home, state.user.position);

  if (pathToUser.length === 0) {
    state.paths.toUser = [];
    state.paths.toGoal = [];
    state.robot.status = "ERROR";
    log("経路探索失敗: 待機位置から利用者位置まで到達できません");
    draw();
    updateStateOutput();
    return false;
  }

  const pathToGoal = findPathBfs(state.user.position, state.goal.position);

  if (pathToGoal.length === 0) {
    state.paths.toUser = pathToUser;
    state.paths.toGoal = [];
    state.robot.status = "ERROR";
    log("経路探索失敗: 利用者位置から目的地まで到達できません");
    draw();
    updateStateOutput();
    return false;
  }

  state.paths.toUser = pathToUser;
  state.paths.toGoal = pathToGoal;
  state.robot.status = "ROUTE_READY";

  log(`経路探索成功: 待機位置→利用者 ${pathToUser.length}マス`);
  log(`経路探索成功: 利用者→目的地 ${pathToGoal.length}マス`);

  draw();
  updateStateOutput();

  return true;
}

function handleCanvasClick(event) {
  const cell = getCellFromMouseEvent(event);

  if (!cell) {
    return;
  }

  log(`クリック座標: (${cell.x}, ${cell.y})`);

  const tool = state.ui.tool;

  if (tool !== "erase" && isWallCell(cell)) {
    log(`壁マスには配置できません: (${cell.x}, ${cell.y})`);
    return;
  }

  if (tool === "home") {
    state.robot.home = { ...cell };
    state.robot.position = { ...cell };
    state.robot.direction = elements.directionSelect.value;
    state.robot.status = "WAITING";
    log(`待機位置を設定: (${cell.x}, ${cell.y}), 向き=${state.robot.direction}`);
  }

  if (tool === "user") {
    state.user.position = { ...cell };
    log(`利用者位置を設定: (${cell.x}, ${cell.y})`);
  }

  if (tool === "goal") {
    state.goal.position = { ...cell };
    log(`目的地を設定: (${cell.x}, ${cell.y})`);
  }

  if (tool === "obstacle") {
    removeObstacleAt(cell);
    state.obstacles.push({ ...cell });
    log(`障害物を設定: (${cell.x}, ${cell.y})`);
  }

  if (tool === "erase") {
    eraseAt(cell);
  }

  draw();
  updateStateOutput();
}

function draw() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  ctx.fillStyle = "#10141d";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  if (state.map.imageLoaded && state.map.image) {
    const layout = getMapLayout();

    ctx.drawImage(
      state.map.image,
      layout.ox,
      layout.oy,
      layout.drawW,
      layout.drawH
    );
  } else {
    ctx.fillStyle = "#ffffff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
  }

  drawGridCells();
  drawPaths();
  drawGridLines();
  drawMarkers();
}

function drawGridCells() {
}

function drawGridLines() {
  if (!state.map.imageLoaded || !state.map.image) {
    return;
  }

  const layout = getMapLayout();
  const cellSizePx = state.map.image.width / state.map.cols;

  ctx.save();
  ctx.translate(layout.ox, layout.oy);
  ctx.scale(layout.scale, layout.scale);

  // evac-sim方式のまま、少し濃くする
  ctx.strokeStyle = "rgb(0, 0, 0)";
  ctx.lineWidth = 0.45;

  for (let y = 0; y <= state.map.rows; y++) {
    ctx.beginPath();
    ctx.moveTo(0, y * cellSizePx);
    ctx.lineTo(state.map.cols * cellSizePx, y * cellSizePx);
    ctx.stroke();
  }

  for (let x = 0; x <= state.map.cols; x++) {
    ctx.beginPath();
    ctx.moveTo(x * cellSizePx, 0);
    ctx.lineTo(x * cellSizePx, state.map.rows * cellSizePx);
    ctx.stroke();
  }

  ctx.restore();
}

function drawMarkers() {
  for (const obstacle of state.obstacles) {
    drawCell(obstacle, "rgba(155, 89, 182, 0.9)", "障");
  }

  if (state.robot.home) {
    drawCell(state.robot.home, "rgba(52, 152, 219, 0.95)", directionSymbol(state.robot.direction));
  }

  if (state.user.position) {
    drawCell(state.user.position, "rgba(231, 76, 60, 0.95)", "人");
  }

  if (state.goal.position) {
    drawCell(state.goal.position, "rgba(46, 204, 113, 0.95)", "G");
  }
}

function drawCell(cell, color, label) {
  if (!state.map.imageLoaded || !state.map.image) {
    return;
  }

  const layout = getMapLayout();
  const cellSizePx = state.map.image.width / state.map.cols;

  const px = layout.ox + cell.x * cellSizePx * layout.scale;
  const py = layout.oy + cell.y * cellSizePx * layout.scale;
  const size = cellSizePx * layout.scale;

  ctx.save();

  ctx.fillStyle = color;
  ctx.fillRect(px, py, size, size);

  ctx.fillStyle = "#ffffff";
  ctx.font = `${Math.max(10, Math.floor(size * 0.5))}px sans-serif`;
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(label, px + size / 2, py + size / 2);

  ctx.restore();
}

function directionSymbol(direction) {
  const symbols = {
    N: "↑",
    E: "→",
    S: "↓",
    W: "←",
  };

  return symbols[direction] ?? "R";
}

function resetAll() {
  state.robot.home = null;
  state.robot.position = null;
  state.robot.direction = "E";
  state.robot.status = "WAITING";
  state.user.position = null;
  state.goal.position = null;
  state.obstacles = [];
  state.paths.toUser = [];
  state.paths.toGoal = [];
  elements.directionSelect.value = "E";

  log("配置を全リセットしました");
  draw();
  updateStateOutput();
}

function handleGuideRequest() {
  if (!state.robot.home) {
    log("案内開始不可: 待機位置が未設定です");
    return;
  }

  if (!state.user.position) {
    log("案内開始不可: 利用者位置が未設定です");
    return;
  }

  if (!state.goal.position) {
    log("案内開始不可: 目的地が未設定です");
    return;
  }

  state.robot.status = "REQUEST_RECEIVED";
  log("案内リクエストを受信しました");

  calculateGuidePaths();
}

function bindEvents() {
  elements.mapFile.addEventListener("change", async (event) => {
    const file = event.target.files?.[0];

    if (!file) return;

    try {
      const image = await loadImageFromFile(file);
      state.map.image = image;
      state.map.imageLoaded = true;
      resizeCanvasToImage();
      log(`画像読み込み成功: ${file.name} (${image.width} x ${image.height})`);
      generateGridFromImage();
    } catch (error) {
      log(error.message);
    }
  });

  elements.thresholdInput.addEventListener("input", () => {
    state.map.threshold = Number(elements.thresholdInput.value);
    elements.thresholdValue.textContent = String(state.map.threshold);
  });

  elements.btnGenerateGrid.addEventListener("click", generateGridFromImage);

  elements.btnParentMode.addEventListener("click", () => setMode("parent"));
  elements.btnClientMode.addEventListener("click", () => setMode("client"));

  elements.toolHome.addEventListener("click", () => setTool("home"));
  elements.toolObstacle.addEventListener("click", () => setTool("obstacle"));
  elements.toolEraseParent.addEventListener("click", () => setTool("erase"));

  elements.toolUser.addEventListener("click", () => setTool("user"));
  elements.toolGoal.addEventListener("click", () => setTool("goal"));
  elements.toolEraseClient.addEventListener("click", () => setTool("erase"));

  elements.directionSelect.addEventListener("change", () => {
    state.robot.direction = elements.directionSelect.value;
    log(`ロボット向きを変更: ${state.robot.direction}`);
    draw();
    updateStateOutput();
  });

  elements.btnGuideRequest.addEventListener("click", handleGuideRequest);
  elements.btnResetAll.addEventListener("click", resetAll);

  elements.btnClearLog.addEventListener("click", () => {
    elements.logOutput.value = "";
  });

  canvas.addEventListener("click", handleCanvasClick);
}

function initCanvas() {
  canvas.width = 720;
  canvas.height = 720;
  state.map.grid = createEmptyGrid(state.map.cols, state.map.rows);
  draw();
}

function init() {
  bindEvents();
  initCanvas();
  setMode("parent");
  setTool("home");
  updateStateOutput();
  log("案内ロボットシミュレーターを起動しました");
}

init();