

def generate_graph(root: Optional[str] = None, dependents: Optional[str] = None, dependencies: Optional[str] = None):
    if g.graph.number_of_nodes() == 0:
        rprint("[yellow]No graph data. Run 'dtm scan' first.[/yellow]")
        return
    
    if dependents:
        result = g.get_all_dependents_recursive(dependents)
        if result:
            console.print(f"[cyan]Packages depending on '{dependents}':[/cyan]")
            for r in sorted(result):
                console.print(f"  - {r}")
        else:
            console.print(f"[yellow]No dependents found for '{dependents}'[/yellow]")
        return
    
    if dependencies:
        result = g.get_all_dependencies_recursive(dependencies)
        if result:
            console.print(f"[cyan]Packages '{dependencies}' depends on:[/cyan]")
            for r in sorted(result):
                console.print(f"  - {r}")
        else:
            console.print(f"[yellow]No dependencies found for '{dependencies}'[/yellow]")
        return
    
    if g.has_cycle():
        console.print("[yellow]Warning: Graph contains cycles![/yellow]")
        cycles = g.get_cycles()
        for cycle in cycles:
            console.print(f"  - {' -> '.join(cycle)}")
    
    tree = g.to_tree_string(root=root)
    console.print(f"\n[bold]Dependency Tree:[/bold]\n{tree}")

    from deepiri_pkg_version_manager.ui.graphDisplay import DependencyGraphView