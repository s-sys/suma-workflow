
{%- set packages = salt['pillar.get']('install_packages', {}) %}
{%- for package, version in packages.items() %}
install_{{ package }}:
  pkg.installed:
    - name: "{{ package }}"
    - version: "{{ version }}"
    - retry:
        attempts: 3
        interval: 15
    - ignore_repo_failure: True
{% endfor %}



