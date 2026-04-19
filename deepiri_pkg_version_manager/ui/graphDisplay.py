from __future__ import annotations

import math
from collections import defaultdict
from typing import Optional

from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsRectItem, QGraphicsPathItem, QGraphicsTextItem
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QFont, QGuiApplication, QPen, QBrush, QColor, QPainter, QPainterPath, QTextOption

from deepiri_pkg_version_manager.graph.dependency_graph import DependencyGraph


class DependencyGraphView(QGraphicsView):
    """Visualizes the same dependency graph as the CLI ``graph`` command.

    Top-level repos (nothing in the graph depends on them) sit in **one or more left columns**,
    filled top-to-bottom with **no vertical gap** between rows; extra columns are added so boxes pack
    into the viewport height instead of leaving empty space between stretched rows. The right column
    stacks the same way from the top. Packages that are declared
    dependencies of others (layer ≥ 1) sit in a **right** column, ordered
    by depth then name. Edges run left→right from a package to its dependencies, or vertically
    within the right column for dependency chains.
    """

    ARROW_SIZE = 18
    FONT_PT_DEPENDENT = 7.5
    FONT_PT_DEFAULT = 10.5
    LAYOUT_MARGIN = 20
    CELL_PAD = 10
    MIN_BOX_WIDTH = 148
    MIN_BOX_HEIGHT = 50
    INTRA_ROW_GAP = 8
    LAYER_GAP = 20
    WINDOW_CHROME_EXTRA = 72

    def __init__(
        self,
        dependency_graph: DependencyGraph,
        root: Optional[str] = None,
    ):
        super().__init__()

        title = "Deepiri Package Version Manager - Graph View"
        if root:
            title = f"{title} (root: {root})"
        self.setWindowTitle(title)
        self.setGeometry(100, 100, 1350, 800)
        self.setMinimumSize(590, 350)

        self.graph = dependency_graph
        self.root_filter = root
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        self.nodes: dict[str, DependencyGraphView.Node] = {}
        self.edges: list[DependencyGraphView.ArrowEdge] = []
        self._by_layer: dict[int, list[str]] = {}
        self._layer_of: dict[str, int] = {}
        self._max_layer: int = 0

        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        self.build_graph()
        self._layout_fill_viewport(allow_grow=False)

    # ----------------------------
    # NODE (labeled box)
    # ----------------------------
    class Node(QGraphicsRectItem):
        def __init__(self, name: str, owner: DependencyGraphView):
            super().__init__()
            self.name = name
            self._owner = owner
            self.out_edges: list[DependencyGraphView.ArrowEdge] = []
            self.in_edges: list[DependencyGraphView.ArrowEdge] = []

            self.setBrush(QBrush(QColor("#2d2d2d")))
            self.setPen(QPen(QColor("#555555"), 2))
            self.setAcceptHoverEvents(True)
            self.setZValue(0)

            self.label = QGraphicsTextItem(self)
            self.label.setDefaultTextColor(QColor("white"))
            self.label.setPlainText(name)
            self.setToolTip(name)

            self._bw = 120.0
            self._bh = 48.0

            self.set_box_size(120, 48)

        def set_box_size(self, w: float, h: float):
            w = max(w, 48.0)
            h = max(h, 32.0)
            self._bw = w
            self._bh = h
            self.prepareGeometryChange()
            self.setRect(-w / 2, -h / 2, w, h)

            self._layout_label()

        def _layout_label(self):
            w, h = self._bw, self._bh
            pad = 8.0
            o = self._owner
            dep_font_pt = o.FONT_PT_DEPENDENT
            default_font_pt = o.FONT_PT_DEFAULT

            is_dependent = len(self.out_edges) > 0

            font = QFont()
            font.setPointSizeF(dep_font_pt if is_dependent else default_font_pt)
            self.label.setFont(font)

            tw = max(w - 2 * pad, 32.0)
            self.label.setTextWidth(tw)
            doc = self.label.document()
            opt = QTextOption()
            opt.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
            opt.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
            doc.setDefaultTextOption(opt)
            self.label.setPlainText(self.name)

            br = self.label.boundingRect()
            self.label.setPos(-br.width() / 2, -br.height() / 2)

        def hoverEnterEvent(self, event):
            self.setBrush(QBrush(QColor("#3a86ff")))
            self.setPen(QPen(QColor("#ffffff"), 2))

            for edge in self.out_edges:
                edge.apply_highlight(True)
                edge.dependency_node.setBrush(QBrush(QColor("#3a86ff")))
                edge.dependency_node.setPen(QPen(QColor("#ffffff"), 2))
            for edge in self.in_edges:
                edge.apply_highlight(True)

            super().hoverEnterEvent(event)

        def hoverLeaveEvent(self, event):
            self.setBrush(QBrush(QColor("#2d2d2d")))
            self.setPen(QPen(QColor("#555555"), 2))

            for edge in self.out_edges:
                edge.apply_highlight(False)
                edge.dependency_node.setBrush(QBrush(QColor("#2d2d2d")))
                edge.dependency_node.setPen(QPen(QColor("#555555"), 2))
            for edge in self.in_edges:
                edge.apply_highlight(False)

            super().hoverLeaveEvent(event)

    # ----------------------------
    # EDGE (dependent → dependency, arrow at dependency)
    # ----------------------------
    class ArrowEdge(QGraphicsPathItem):
        def __init__(
            self,
            dependent: DependencyGraphView.Node,
            dependency: DependencyGraphView.Node,
            arrow_size: float,
        ):
            super().__init__()
            self.dependent_node = dependent
            self.dependency_node = dependency
            self.arrow_size = arrow_size
            self._base_pen = QPen(QColor("#e8e8e8"), 3.0)
            self._base_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            self._base_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            self._hi_pen = QPen(QColor("#5cadff"), 4.0)
            self._hi_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            self._hi_pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            self._base_brush = QBrush(QColor("#f0f0f0"))
            self._hi_brush = QBrush(QColor("#7ec8ff"))
            self.setPen(self._base_pen)
            self.setBrush(self._base_brush)
            self.setZValue(-1)

            dependent.out_edges.append(self)
            dependency.in_edges.append(self)

            self.update_position()

        def apply_highlight(self, on: bool):
            self.setPen(self._hi_pen if on else self._base_pen)
            self.setBrush(self._hi_brush if on else self._base_brush)

        def update_position(self):
            ra = self.dependent_node.sceneBoundingRect()
            rb = self.dependency_node.sceneBoundingRect()
            cax, cay = ra.center().x(), ra.center().y()
            cbx, cby = rb.center().x(), rb.center().y()
            dx_mid = cbx - cax
            col_eps = 24.0

            if dx_mid > col_eps:
                sx, sy = ra.right(), cay
                tx, ty = rb.left(), cby
            elif dx_mid < -col_eps:
                sx, sy = ra.left(), cay
                tx, ty = rb.right(), cby
            elif cay <= cby:
                sx, sy = cax, ra.bottom()
                tx, ty = cbx, rb.top()
            else:
                sx, sy = cax, ra.top()
                tx, ty = cbx, rb.bottom()

            dx = tx - sx
            dy = ty - sy
            length = math.hypot(dx, dy)
            if length < 1e-6:
                self.prepareGeometryChange()
                self.setPath(QPainterPath())
                return

            ux, uy = dx / length, dy / length
            px, py = -uy, ux

            margin = 2.0
            x1 = sx + ux * margin
            y1 = sy + uy * margin
            tip = QPointF(tx - ux * margin, ty - uy * margin)
            asz = self.arrow_size
            base = QPointF(tip.x() - ux * asz, tip.y() - uy * asz)
            wing = asz * 0.5
            p1 = QPointF(base.x() + px * wing, base.y() + py * wing)
            p2 = QPointF(base.x() - px * wing, base.y() - py * wing)

            path = QPainterPath()
            path.moveTo(x1, y1)
            path.lineTo(base.x(), base.y())
            path.moveTo(tip)
            path.lineTo(p1)
            path.lineTo(p2)
            path.closeSubpath()

            self.prepareGeometryChange()
            self.setPath(path)

        def boundingRect(self) -> QRectF:
            return self.path().boundingRect().normalized().adjusted(-2, -2, 2, 2)

    # ----------------------------
    # BUILD GRAPH
    # ----------------------------
    def _node_names(self) -> list[str]:
        names = []
        for nid in self.graph.graph.nodes:
            n = self.graph.get_node_name(nid)
            if n:
                names.append(n)
        return names

    def _subtree_names(self, root: str) -> set[str]:
        out: set[str] = set()
        stack = [root]
        while stack:
            name = stack.pop()
            if name in out:
                continue
            out.add(name)
            for child in self.graph.get_dependencies(name):
                stack.append(child)
        return out

    def _compute_layers(self, names: set[str]) -> dict[str, int]:
        """Row index: 0 = top (roots / packages nothing else depends on in this view).
        Each package sits one row below the deepest row of any package that depends on it,
        so a shared dependency appears under all of its dependents (DAG longest-path layering).
        """
        g = self.graph
        memo: dict[str, int] = {}
        visiting: set[str] = set()

        def layer_for(n: str) -> int:
            if n not in names:
                return 0
            if n in memo:
                return memo[n]
            if n in visiting:
                return 0
            visiting.add(n)
            preds = [p for p in g.get_dependents(n) if p in names]
            if not preds:
                d = 0
            else:
                d = max(layer_for(p) for p in preds) + 1
            visiting.remove(n)
            memo[n] = d
            return d

        for n in names:
            layer_for(n)
        return memo

    def build_graph(self):
        g = self.graph
        if g.graph.number_of_nodes() == 0:
            return

        children_map: defaultdict[str, list[str]] = defaultdict(list)
        if self.root_filter is not None:
            if g.get_node_id(self.root_filter) is None:
                return
            names = self._subtree_names(self.root_filter)
            for name in names:
                for child in g.get_dependencies(name):
                    if child in names:
                        children_map[name].append(child)
        else:
            names = set(self._node_names())
            for name in names:
                for child in g.get_dependencies(name):
                    children_map[name].append(child)

        layers = self._compute_layers(names)
        self._layer_of = layers
        by_layer: defaultdict[int, list[str]] = defaultdict(list)
        for name in names:
            by_layer[layers[name]].append(name)
        for lv in by_layer:
            by_layer[lv].sort()
        self._by_layer = dict(by_layer)
        self._max_layer = max(by_layer.keys(), default=0)

        for name in names:
            self.nodes[name] = self.Node(name, self)
            self.scene.addItem(self.nodes[name])

        seen_edges: set[tuple[str, str]] = set()
        for parent, children in children_map.items():
            for child in children:
                if parent not in self.nodes or child not in self.nodes:
                    continue
                key = (parent, child)
                if key in seen_edges:
                    continue
                seen_edges.add(key)
                edge = self.ArrowEdge(
                    self.nodes[parent],
                    self.nodes[child],
                    arrow_size=self.ARROW_SIZE,
                )
                self.scene.addItem(edge)
                self.edges.append(edge)

    # ----------------------------
    # LAYOUT — parent repos (layer 0) in multiple left columns; dependencies (layer ≥ 1) right column
    # ----------------------------
    def _layout_fill_viewport(self, allow_grow: bool = True):
        if not self.nodes or not self._layer_of:
            return

        vp = self.viewport().rect()
        vw = max(float(vp.width()), 400.0)
        vh = max(float(vp.height()), 280.0)

        margin = self.LAYOUT_MARGIN
        min_bw = self.MIN_BOX_WIDTH
        min_bh = self.MIN_BOX_HEIGHT
        bw = max(min_bw - 4.0, 120.0)
        bh = max(min_bh - 4.0, 40.0)
        h_gap = float(self.CELL_PAD)
        usable_h = max(vh - 2.0 * margin, bh + 1.0)
        row_stride = bh

        right_cx = vw - margin - bw / 2.0
        min_mid_gap = 96.0
        first_left_cx = margin + bw / 2.0
        max_span = right_cx - margin - 2.0 * bw - min_mid_gap
        slot_w = bw + h_gap
        max_cols_width = max(1, int(max_span / slot_w) + 1) if max_span >= 0 else 1

        max_rows_fit = max(1, int(usable_h / bh)) if usable_h >= bh else 1

        parent_repos = sorted(
            (n for n in self.nodes if self._layer_of.get(n, 0) == 0),
            key=str,
        )
        right_side = sorted(
            (n for n in self.nodes if self._layer_of.get(n, 0) >= 1),
            key=lambda n: (self._layer_of[n], n),
        )

        max_bottom = margin

        n_parents = len(parent_repos)
        if n_parents > 0:
            min_cols_for_height = max(1, int(math.ceil(n_parents / max_rows_fit)))
            n_left_cols = min(max_cols_width, min_cols_for_height)
            n_left_cols = max(1, n_left_cols)
            rows = int(math.ceil(n_parents / n_left_cols))
            row_y = [margin + bh / 2.0 + r * row_stride for r in range(rows)]
            for i, name in enumerate(parent_repos):
                c = i // rows
                r = i % rows
                cx = first_left_cx + c * slot_w
                cy = row_y[r]
                node = self.nodes[name]
                node.set_box_size(bw, bh)
                node.setPos(QPointF(cx, cy))
                max_bottom = max(max_bottom, cy + bh / 2.0)

        n_right = len(right_side)
        if n_right > 0:
            for j, name in enumerate(right_side):
                cy = margin + bh / 2.0 + j * row_stride
                node = self.nodes[name]
                node.set_box_size(bw, bh)
                node.setPos(QPointF(right_cx, cy))
                max_bottom = max(max_bottom, cy + bh / 2.0)

        scene_w = vw
        scene_h = max(vh, max_bottom + margin)
        self.setSceneRect(0.0, 0.0, scene_w, scene_h)

        if allow_grow:
            self._grow_window_if_needed(int(scene_h), int(scene_w))

        self._update_edges()

    def _grow_window_if_needed(self, scene_h: int, scene_w: int) -> None:
        """Expand the window only when content is larger (within available screen); never shrink user-resized windows."""
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        avail = screen.availableGeometry()
        margin = self.LAYOUT_MARGIN
        cap_h = avail.height() - 24
        cap_w = avail.width() - 24
        need_h = min(scene_h + self.WINDOW_CHROME_EXTRA, cap_h)
        need_w = min(scene_w + margin, cap_w)
        nw = self.width()
        nh = self.height()
        if need_w > nw:
            nw = need_w
        if need_h > nh:
            nh = need_h
        if nw != self.width() or nh != self.height():
            self.resize(int(nw), int(nh))

    def _update_edges(self):
        for e in self.edges:
            e.update_position()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_fill_viewport(allow_grow=False)

    def showEvent(self, event):
        super().showEvent(event)
        self._layout_fill_viewport(allow_grow=True)
