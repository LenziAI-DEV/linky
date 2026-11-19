"""Escape do formato *little* do LinkedIn (campo `commentary` de /rest/posts).

Fonte de verdade: a lista de caracteres reservados da documentação do LinkedIn
(`| { } @ [ ] ( ) < > # \\ * _ ~`) e o T3, em que hashtags sem escape saíram clicáveis.
"""

from linky_agents.little import escape_little


def test_texto_sem_reservados_nao_muda():
    texto = "Durante seis meses, uma equipe revisou a IA.\n\n• Começo pelo simples\n→ Ação"
    assert escape_little(texto) == texto


def test_reservados_recebem_barra_invertida():
    assert escape_little("(80%) [x] {y} <z> a|b @nubank *s* _i_ ~t~") == (
        r"\(80%\) \[x\] \{y\} \<z\> a\|b \@nubank \*s\* \_i\_ \~t\~"
    )


def test_barra_invertida_e_escapada_antes_das_outras():
    assert escape_little(r"C:\pasta (1)") == r"C:\\pasta \(1\)"


def test_hashtag_continua_clicavel_e_cerquilha_solta_e_escapada():
    assert escape_little("#InteligenciaArtificial #FuturoDoTrabalho") == (
        "#InteligenciaArtificial #FuturoDoTrabalho"
    )
    assert escape_little("#Negócios") == "#Negócios"
    assert escape_little("nota # 3 e C#") == r"nota \# 3 e C\#"


def test_mencao_aprovada_fica_intacta_e_o_resto_e_escapado():
    # Post da Bain, 13/11/2026: as menções saíram clicáveis, mas os parênteses sem escape
    # cortaram a legenda em "produtividade"
    texto = (
        "pesquisa da @[Bain & Company](urn:li:organization:2114) e da "
        "@[Fulano](urn:li:person:AbC-12_x): produtividade (56%) lidera"
    )
    assert escape_little(texto) == (
        "pesquisa da @[Bain & Company](urn:li:organization:2114) e da "
        r"@[Fulano](urn:li:person:AbC-12_x): produtividade \(56%\) lidera"
    )


def test_arroba_ou_colchete_fora_do_formato_de_mencao_e_escapado():
    assert escape_little("@[Adobe] e [x](y)") == r"\@\[Adobe\] e \[x\]\(y\)"
