# h1-scope

Exporta a política, os ativos e as exclusões de programas da HackerOne para Markdown, pronto para consulta pelo Strix. Também salva um JSON com os dados originais da API, percorrendo toda a paginação.

## Uso

Requer Python 3.9+; não precisa instalar bibliotecas.

```bash
git clone https://github.com/GalakCV/h1-scope.git
cd h1-scope
python3 h1_scope.py whatnot --username SEU_API_USERNAME --output-dir output
```

Digite o API token quando solicitado; ele não será exibido. Também aceita `H1_API_USERNAME` e `H1_API_TOKEN` como variáveis de ambiente. Use o identificador associado ao token na HackerOne.

Arquivos gerados: `output/whatnot-scope.md` e `output/whatnot-scope.json`. Para outro programa, troque `whatnot` pelo handle ou pela URL do programa.

```bash
strix --target "https://ALVO_CONFIRMADO_NO_ESCOPO" --instruction-file output/whatnot-scope.md
```

Revise a política antes de testar: o script preserva o texto original, mas não interpreta automaticamente rate limits, headers ou janelas de teste e não consulta documentos externos referenciados. O arquivo é um retrato da data da consulta. Nenhum teste contra os alvos é iniciado pelo exportador.

Não publique tokens nem resultados de programas privados.
