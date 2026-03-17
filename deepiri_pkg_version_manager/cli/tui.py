from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Header, Footer, Static, ListView, ListItem, Tree
from textual.binding import Binding

from ..deps.dependency_registry import DependencyRegistry
from ..tags.tag_manager import TagManager


class DependencyList(ListView):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.registry = DependencyRegistry()

    def watch_focused(self, focused) -> None:
        if focused:
            self.app.refresh_graph(self.focused.item.to_text() if self.focused.item else None)


class TUIApp(App):
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("/", "focus_search", "Search"),
    ]

    def __init__(self):
        super().__init__()
        self.registry = DependencyRegistry()
        self.tag_manager = TagManager()

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="sidebar", classes="sidebar"):
                yield Static("Dependencies", classes="panel-title")
                yield ListView(id="dep-list", classes="dep-list")
            with Vertical(id="main"):
                yield Static("Dependency Graph", classes="panel-title")
                with Container(id="graph-container"):
                    yield Static(id="graph-view", classes="graph-view")
                with Container(id="tag-panel"):
                    yield Static("Tags", classes="panel-title")
                    yield ListView(id="tag-list", classes="tag-list")
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_deps()
        self.refresh_tags()

    def refresh_deps(self):
        list_view = self.query_one("#dep-list", ListView)
        list_view.clear()
        
        deps = self.registry.get_all()
        for dep in deps:
            list_view.append(ListItem(Static(dep.name)))

    def refresh_tags(self):
        list_view = self.query_one("#tag-list", ListView)
        list_view.clear()
        
        tags = self.tag_manager.get_all_tags()
        for tag in tags:
            list_view.append(ListItem(Static(tag.name)))

    def refresh_graph(self, dep_name: str | None):
        graph_view = self.query_one("#graph-view", Static)
        
        if not dep_name:
            g = self.registry.build_graph()
            graph_view.update(g.to_tree_string())
        else:
            g = self.registry.build_graph()
            deps = g.get_dependencies(dep_name)
            dependents = g.get_dependents(dep_name)
            
            text = f"[bold]{dep_name}[/bold]\n\n"
            text += f"[cyan]Dependencies:[/cyan]\n"
            for d in deps:
                text += f"  → {d}\n"
            text += f"\n[magenta]Dependents:[/magenta]\n"
            for d in dependents:
                text += f"  ← {d}\n"
            
            graph_view.update(text)

    def action_refresh(self):
        self.refresh_deps()
        self.refresh_tags()

    def action_quit(self):
        self.exit()


if __name__ == "__main__":
    app = TUIApp()
    app.run()
