import asyncio
import traceback
import pandas as pd
import os
from datetime import datetime
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import tempfile
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

app = Flask(__name__)
CORS(app)

# Global variable to store automation task (for simplicity, in production use a task queue)
current_task = None

class WebAutomation:
    def __init__(self):
        self.visitas_extraidas = []
        self.browser = None
        self.page = None

    async def setup_browser(self):
        """Configura o navegador com Playwright"""
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(headless=True)
        self.page = await self.browser.new_page()
        await self.page.set_viewport_size({"width": 1280, "height": 720})

    async def accept_cookies(self):
        """Aceita cookies se aparecerem"""
        try:
            # Aguardar um breve momento para possíveis popups
            await self.page.wait_for_timeout(1000)
            # Tentar clicar em botões de aceitar cookies
            buttons = await self.page.query_selector_all('button')
            for button in buttons:
                text = await button.text_content()
                if text and any(word in text.lower() for word in ["aceitar", "accept", "concordo", "ok"]):
                    await button.click()
                    print("🍪 Cookies aceitos")
                    await self.page.wait_for_timeout(1000)
                    break
        except Exception as e:
            print("ℹ️ Nenhum botão de cookies encontrado ou erro:", e)

    async def navigate_to_section(self, section_name, selector):
        """Navega para uma seção específica do sistema"""
        try:
            print(f"📜 Navegando para: {section_name}")
            element = await self.page.wait_for_selector(selector, timeout=30000)
            await element.click()
            print(f"✅ {section_name} acessado com sucesso")
            await self.page.wait_for_timeout(1500)
        except Exception as e:
            print(f"❌ Erro ao acessar {section_name}: {str(e)}")
            raise

    async def reconectar_iframe_principal(self):
        """Reconecta ao iframe principal"""
        try:
            # Voltar ao contexto principal
            await self.page.wait_for_timeout(1000)
            # Tenta encontrar o iframe com 'visitaDomiciliar' no src
            iframe_element = await self.page.wait_for_selector('iframe[src*="visitaDomiciliar"]', timeout=10000)
            if iframe_element:
                frame = await iframe_element.content_frame()
                self.page = frame
                print("✅ Reconectado ao iframe principal")
                return True
            else:
                print("❌ Nenhum iframe encontrado")
                return False
        except Exception as e:
            print(f"⚠️ Erro ao reconectar iframe: {str(e)}")
            return False

    async def get_current_page(self):
        """Obtém o número da página atual ativa"""
        try:
            elemento_ativo = await self.page.wait_for_selector('div.paginator-page.active b', timeout=5000)
            texto = await elemento_ativo.text_content()
            return int(texto)
        except Exception as e:
            print(f"⚠️ Não foi possível obter a página atual: {str(e)}")
            return None

    async def corrigir_navegacao_pagina(self, pagina_desejada):
        """Corrige a navegação com múltiplas estratégias"""
        max_tentativas = 5
        tentativa = 0
        
        while tentativa < max_tentativas:
            try:
                pagina_atual = await self.get_current_page()
                if pagina_atual is None:
                    print("❌ Não foi possível determinar a página atual")
                    return False
                    
                print(f"🔢 Página atual: {pagina_atual}, Desejada: {pagina_desejada}")
                
                if pagina_atual == pagina_desejada:
                    print("✅ Já está na página desejada")
                    return True
                
                # Estratégia 1: Busca direta pelo número da página
                try:
                    botao_pagina = await self.page.wait_for_selector(f'div.paginator-page b:has-text("{pagina_desejada}")', timeout=5000)
                    await botao_pagina.click()
                    print(f"✅ Clicou diretamente na página {pagina_desejada}")
                    await self.page.wait_for_timeout(3000)
                    
                    # Verifica se navegou corretamente
                    nova_pagina = await self.get_current_page()
                    if nova_pagina == pagina_desejada:
                        return True
                except Exception as e:
                    print(f"❌ Erro ao clicar diretamente: {e}")

                # Estratégia 2: Navegação sequencial para páginas próximas
                diferenca = pagina_desejada - pagina_atual
                if abs(diferenca) <= 5:  # Para navegações curtas
                    direcao = "next" if diferenca > 0 else "prev"
                    for _ in range(abs(diferenca)):
                        try:
                            if direcao == "next":
                                botao = await self.page.wait_for_selector('div.paginator-next', timeout=5000)
                            else:
                                botao = await self.page.wait_for_selector('div.paginator-prev', timeout=5000)
                            
                            await botao.click()
                            await self.page.wait_for_timeout(2000)
                        except Exception as e:
                            print(f"⚠️ Erro na navegação sequencial: {e}")
                            break
                    
                    # Verifica resultado
                    nova_pagina = await self.get_current_page()
                    if nova_pagina == pagina_desejada:
                        return True
                
                tentativa += 1
                await self.page.wait_for_timeout(2000)
                
            except Exception as e:
                print(f"❌ Erro na tentativa {tentativa + 1}: {e}")
                tentativa += 1
                await self.page.wait_for_timeout(1000)
        
        print(f"❌ Falha após {max_tentativas} tentativas")
        return False

    async def clicar_lupa_com_tentativas(self, elemento, descricao):
        """Tenta clicar em uma lupa com múltiplas estratégias"""
        tentativas = 3
        for tentativa in range(tentativas):
            try:
                # Rolando até o elemento
                await elemento.scroll_into_view_if_needed()
                await self.page.wait_for_timeout(1000)
                
                # Tentativa 1: Clique normal
                await elemento.click()
                await self.page.wait_for_timeout(2000)
                return True
                
            except Exception as e:
                print(f"⚠️ Tentativa {tentativa + 1} falhou para {descricao}: {e}")
                
                # Tentativa 2: JavaScript click
                try:
                    await self.page.evaluate("(element) => element.click()", elemento)
                    await self.page.wait_for_timeout(2000)
                    return True
                except:
                    pass
                
                await self.page.wait_for_timeout(1000)
        
        return False

    async def navegar_para_pagina(self, pagina):
        """Navega para uma página específica"""
        print(f"🔄 Navegando para página {pagina}...")
        
        # Estratégia 1: Busca direta pelo número
        try:
            botao = await self.page.wait_for_selector(f'div.paginator-page b:has-text("{pagina}")', timeout=10000)
            await self.page.evaluate("(element) => element.click()", botao)
            await self.page.wait_for_timeout(4000)
            return True
        except:
            pass
        
        # Estratégia 2: Navegação sequencial a partir da página atual
        return await self.corrigir_navegacao_pagina(pagina)

    async def processar_lupas_secundarias(self):
        """Processa as lupas secundárias (detalhes)"""
        try:
            # Buscar lupas secundárias
            lupas_sec = await self.page.query_selector_all('div.noselect[style*="view.png"]')
            lupas_sec = [l for l in lupas_sec if await l.is_visible()]
            
            print(f"🔎 Encontradas {len(lupas_sec)} lupas secundárias")
            
            for j, lupa_sec in enumerate(lupas_sec):
                print(f"  📋 Processando detalhe {j + 1} de {len(lupas_sec)}")
                
                try:
                    if await self.clicar_lupa_com_tentativas(lupa_sec, f"lupa secundária {j + 1}"):
                        await self.page.wait_for_timeout(4000)
                        
                        # Extrair dados
                        if await self.extrair_dados_ficha():
                            print("  ✅ Dados extraídos com sucesso")
                        else:
                            print("  ⚠️ Falha na extração de dados")
                        
                        # Voltar
                        await self.page.go_back()
                        await self.page.wait_for_timeout(3000)
                        await self.reconectar_iframe_principal()
                        
                except Exception as e:
                    print(f"  ❌ Erro no detalhe {j + 1}: {e}")
                    continue
                    
        except Exception as e:
            print(f"  ❌ Erro ao processar lupas secundárias: {e}")

    async def extrair_dados_ficha(self):
        """Extrai todos os dados da ficha de visita"""
        try:
            print("\n📝 Iniciando extração completa de dados...")
            try:
                await self.page.wait_for_selector('text="CPF/CNS do cidadão"', timeout=10000)
            except PlaywrightTimeoutError:
                print("⚠️ Formulário não carregou completamente")
                return False

            dados = {
                "Desfecho": await self._extrair_radio_por_rotulo_extjs(["Visita realizada", "Visita recusada", "Ausente"]),
                "Data da visita": await self._extrair_valor_por_rotulo(["Data"]),
                "Turno": await self._extrair_radio_por_rotulo_extjs(["Manhã", "Tarde", "Noite"]),
                "Nº do prontuário": await self._extrair_valor_por_rotulo(["Nº do prontuário"]),
                "CPF/CNS": await self._extrair_valor_por_rotulo(["CPF/CNS do cidadão", "CPF / CNS do cidadão"]),
                "Nascimento": await self._extrair_valor_por_rotulo(["Data de nascimento"]),
                "Sexo": await self._extrair_valor_input_disabled_por_peid("FichaVisitaDomiciliarChildForm.sexo"),
                "Glicemia capilar": await self._extrair_valor_por_rotulo(["Glicemia capilar (mg/dL)"]),
                "Momento da coleta": await self._extrair_radio_por_rotulo_extjs(["Não especificado", "Jejum", "Pré-prandial", "Pós-prandial"]),
                "Peso": await self._extrair_valor_por_rotulo(["Peso (kg)"]),
                "Altura": await self._extrair_valor_por_rotulo(["Altura (cm)"]),
                "Temperatura": await self._extrair_valor_por_rotulo(["Temperatura (ºC)"]),
                "Pressão arterial": await self._extrair_pressao_arterial_completa()
            }
            
            # Caixas de seleção (checkboxes)
            checkboxes = [
                "Visita compartilhada com outro profissional",
                "Cadastramento / Atualização",
                "Visita periódica",
                "Consulta",
                "Exame",
                "Vacina",
                "Condicionalidades do Bolsa Família",                
                "Gestante",
                "Puérpera",
                "Recém-nascido",
                "Criança",
                "Pessoa com desnutrição",
                "Pessoa em reabilitação ou com deficiência",
                "Pessoa com hipertensão",
                "Pessoa com diabetes",
                "Pessoa com asma",
                "Pessoa com DPOC / enfisema",
                "Pessoa com câncer",
                "Pessoa com outras doenças crônicas",
                "Pessoa com hanseníase",
                "Pessoa com tuberculose",
                "Sintomáticos respiratórios",
                "Tabagista",
                "Domiciliados / Acamados",
                "Condições de vulnerabilidade social",
                "Condicionalidades do Bolsa Família",
                "Saúde mental",
                "Usuário de álcool",
                "Usuário de outras drogas",
                "Pessoa idosa",
                "Ação educativa",
                "Imóvel com foco",
                "Ação mecânica",
                "Tratamento focal",
                "Egresso de internação",
                "Convite para atividades coletivas / campanha de saúde",
                "Orientação / Prevenção",
                "Outros"
            ]
            
            # Status das checkboxes
            for checkbox in checkboxes:
                resultados = await self._verificar_checkbox(checkbox) or ["Não encontrado"]
                if checkbox == "Condicionalidades do Bolsa Família":
                    for i, resultado in enumerate(resultados, 1):
                        dados[f"{checkbox} {i}"] = resultado
                else:
                    dados[checkbox] = resultados[0]
            
            print("✅ Dados extraídos com sucesso")
            self.visitas_extraidas.append(dados)
            return True
            
        except Exception as e:
            print(f"❌ Erro na extração: {str(e)}")
            await self.page.screenshot(path="erro_extracao.png")
            traceback.print_exc()
            return False

    async def _extrair_pressao_arterial_completa(self):
        """Extrai especificamente a pressão arterial no formato completo"""
        try:
            # Tenta encontrar os dois inputs da pressão arterial
            inputs = await self.page.query_selector_all('text="Pressão arterial" >> xpath=..//input')
            
            if len(inputs) >= 2:
                sistolica = await inputs[0].get_attribute("value") or ""
                diastolica = await inputs[1].get_attribute("value") or ""
                
                if sistolica and diastolica:
                    return f"{sistolica}/{diastolica}"
            
            return ""
        except Exception as e:
            print(f"⚠️ Erro ao extrair pressão arterial completa: {str(e)}")
            return ""

    async def _extrair_valor_por_rotulo(self, rotulos):
        """Extrai valores de campos de input por um ou mais rótulos possíveis"""
        if isinstance(rotulos, str):
            rotulos = [rotulos]
            
        for rotulo in rotulos:
            try:
                # Tenta encontrar primeiro como input normal
                elemento = await self.page.query_selector(f'text="{rotulo}" >> xpath=..//input')
                if elemento:
                    valor = await elemento.get_attribute("value")
                    if valor:
                        return valor
                    
                # Se não encontrar, tenta como input readonly
                elemento = await self.page.query_selector(f'text="{rotulo}" >> xpath=..//div[contains(@class, "readonly")]//input')
                if elemento:
                    return await elemento.get_attribute("value")
            except Exception as e:
                continue
                
        print(f"⚠️ Campo com rótulos {rotulos} não encontrado")
        return ""

    async def _extrair_radio_por_rotulo_extjs(self, rotulos):
        """Extrai opção selecionada de radio button no ExtJS por um ou mais rótulos possíveis"""
        if isinstance(rotulos, str):
            rotulos = [rotulos]
            
        for rotulo in rotulos:
            try:
                # Encontra o container principal do grupo de radio buttons
                container = await self.page.query_selector(f'label:has-text("{rotulo}") >> xpath=../..')
                
                # Procura o radio button selecionado dentro do container
                radio_selecionado = await container.query_selector('input[type="radio"]:checked')
                
                if radio_selecionado:
                    # Obtém o label associado ao radio button selecionado
                    label = await radio_selecionado.query_selector('xpath=./following-sibling::label[1]')
                    if label:
                        texto = await label.text_content()
                        return texto.strip()
                
            except Exception as e:
                continue
                
        print(f"⚠️ Radio button com rótulos {rotulos} não encontrado (ExtJS)")
        return ""

    async def _verificar_checkbox(self, rotulo):
        """
        Verifica se uma ou mais checkboxes com o mesmo rótulo estão marcadas.
        Retorna sempre uma lista de strings ("Sim", "Não", "Erro" ou "Não encontrado").
        """
        try:
            estados = []
            labels = await self.page.query_selector_all(f'label:has-text("{rotulo}")')
            for label in labels:
                checkbox_id = await label.get_attribute("for")
                if checkbox_id:
                    try:
                        checkbox = await self.page.query_selector(f'#{checkbox_id}')
                        if checkbox:
                            marcado = await checkbox.is_checked()
                            estados.append("Sim" if marcado else "Não")
                        else:
                            estados.append("Erro")
                    except Exception as e:
                        print(f"⚠️ Erro ao verificar checkbox com ID '{checkbox_id}': {e}")
                        estados.append("Erro")
                else:
                    # Tenta encontrar o checkbox diretamente pelo label
                    checkbox = await label.query_selector('input[type="checkbox"]')
                    if checkbox:
                        marcado = await checkbox.is_checked()
                        estados.append("Sim" if marcado else "Não")
                    else:
                        estados.append("Erro")

            if not estados:
                print(f"⚠️ Nenhuma label encontrada para '{rotulo}'")
                return ["Não encontrado"]
            return estados

        except Exception as e:
            print(f"❌ Erro inesperado em _verificar_checkbox('{rotulo}'): {e}")
            return ["Erro inesperado"]

    async def _extrair_valor_input_disabled_por_peid(self, peid):
        """Extrai valor de um campo desabilitado pelo atributo peid"""
        try:
            campo = await self.page.query_selector(f'[peid="{peid}"] input[disabled]')
            if campo:
                valor = await campo.get_attribute("value")
                return valor.strip()
            return ""
        except Exception as e:
            print(f"⚠️ Erro ao extrair campo desabilitado com peid '{peid}': {str(e)}")
            return ""

    async def processar_lupas(self, paginas_selecionadas=None):
        """Processa fichas nas páginas selecionadas com melhor tratamento de erros"""
        try:
            if not paginas_selecionadas:
                print("⚠️ Nenhuma página selecionada. Processando apenas a página 1.")
                paginas_selecionadas = [1]

            print(f"\n🔍 Iniciando processamento de {len(paginas_selecionadas)} páginas...")
            
            for pagina in sorted(paginas_selecionadas):
                print(f"\n{'='*50}")
                print(f"📄 PROCESSANDO PÁGINA {pagina}")
                print(f"{'='*50}")

                # Navegação para páginas além da primeira
                if pagina > 1:
                    if not await self.navegar_para_pagina(pagina):
                        print(f"❌ Não foi possível acessar a página {pagina}, pulando...")
                        continue

                # Localizar lupas com timeout maior
                try:
                    await self.page.wait_for_selector('div.noselect[style*="view.png"]', timeout=15000)
                    lupas = await self.page.query_selector_all('div.noselect[style*="view.png"]')
                    lupas = [lupa for lupa in lupas if await lupa.is_visible()]
                    total_lupas = len(lupas)
                    
                    if total_lupas == 0:
                        print(f"⚠️ Nenhuma lupa encontrada na página {pagina}")
                        continue
                        
                    print(f"✅ Encontradas {total_lupas} fichas na página {pagina}")
                    
                except PlaywrightTimeoutError:
                    print(f"❌ Timeout ao buscar lupas na página {pagina}")
                    continue

                # Processar cada lupa
                for indice_lupa in range(total_lupas):
                    print(f"\n📝 Processando ficha {indice_lupa + 1} de {total_lupas}")
                    
                    try:
                        # Re-localizar lupas a cada iteração
                        lupas_atual = await self.page.query_selector_all('div.noselect[style*="view.png"]')
                        lupas_atual = [l for l in lupas_atual if await l.is_visible()]
                        
                        if indice_lupa >= len(lupas_atual):
                            print("⚠️ Índice inválido, continuando...")
                            continue

                        # Clicar na lupa principal
                        if not await self.clicar_lupa_com_tentativas(lupas_atual[indice_lupa], f"lupa principal {indice_lupa + 1}"):
                            print(f"❌ Falha ao clicar na lupa {indice_lupa + 1}, pulando...")
                            continue

                        await self.page.wait_for_timeout(4000)  # Espera para carregar

                        # Processar lupas secundárias
                        await self.processar_lupas_secundarias()

                        # Voltar para lista principal
                        await self.page.go_back()
                        await self.page.wait_for_timeout(4000)
                        await self.reconectar_iframe_principal()

                    except Exception as e:
                        print(f"⚠️ Erro na ficha {indice_lupa + 1}: {e}")
                        # Tenta recuperar voltando para a lista
                        try:
                            await self.page.go_back()
                            await self.page.wait_for_timeout(3000)
                            await self.reconectar_iframe_principal()
                        except:
                            pass
                        continue

            print("\n✅ Processamento de todas as páginas concluído!")
            return True

        except Exception as e:
            print(f"❌ Erro crítico no processamento: {e}")
            return False

    async def run_automation(self, url, user, password, cns, paginas_selecionadas):
        """Fluxo principal da automação"""
        try:
            # Verifica se o browser foi configurado corretamente
            if self.page is None:
                print("❌ Erro: Browser não foi configurado corretamente")
                return False
                
            # 1. Acessar o sistema (usando o URL fornecido)
            await self.page.goto(url)
            print(f"🌐 Página inicial carregada: {url}")
            await self.accept_cookies()

            # 2. Fazer login
            print("🔐 Fazendo login...")
            await self.page.fill('input[name="username"]', user)
            await self.page.fill('input[name="password"]', password)
            await self.page.keyboard.press('Enter')
            print("✅ Login realizado")
            await self.page.wait_for_timeout(2000)

            # 2.5. Verifica se está logado em outra sessão
            try:
                print("⏳ Verificando se há sessão anterior ativa...")
                btn_continuar = await self.page.wait_for_selector('button:has-text("Continuar")', timeout=5000)
                await btn_continuar.click()
                print("🔁 Sessão anterior detectada e continuada com sucesso.")
                await self.page.wait_for_timeout(2000)
            except PlaywrightTimeoutError:
                print("✅ Nenhuma sessão anterior ativa detectada.")

            # 3. Tentar selecionar unidade (com tratamento se não aparecer)
            try:
                print("🏥 Tentando selecionar unidade...")
                unidade = await self.page.wait_for_selector('div.css-13q30a h3', timeout=10000)
                await unidade.click()
                print("✅ Unidade selecionada")
                await self.page.wait_for_timeout(2000)
            except PlaywrightTimeoutError:
                print("⚠️ Elemento de seleção de unidade não encontrado. Continuando...")
            except Exception as e:
                print(f"⚠️ Erro ao tentar selecionar unidade: {str(e)}. Continuando...")

            # 4. Navegar até a seção de visitas
            await self.navigate_to_section("Menu CDS", 'a[data-cy="SideMenu.CDS"]')
            await self.navigate_to_section("Visitas Domiciliares", 'span:has-text("Visita domiciliar")')
            await self.page.wait_for_timeout(3000)

            # 5. Conectar ao iframe principal
            print("🗺️ Conectando ao iframe principal...")
            if not await self.reconectar_iframe_principal():
                raise Exception("Falha ao conectar ao iframe principal")
            await self.page.wait_for_timeout(2000)

            # 6. Preencher formulário de pesquisa
            print("✍️ Preenchendo formulário de pesquisa...")
            cns_input = await self.page.wait_for_selector('input[type="text"]:not([disabled])')
            await cns_input.fill(cns)
            
            checkbox = await self.page.wait_for_selector('input[type="checkbox"]')
            if not await checkbox.is_checked():
                await checkbox.click()
            
            btn_pesquisar = await self.page.wait_for_selector('button:has-text("Pesquisar")')
            await btn_pesquisar.click()
            await self.page.wait_for_timeout(3000)
            
            print(f"\n🔍 Processando páginas selecionadas: {paginas_selecionadas}...")
            await self.processar_lupas(paginas_selecionadas=paginas_selecionadas)
            
            if self.visitas_extraidas:
                # Aqui você pode processar os dados como antes, mas vamos retornar o DataFrame
                df = pd.DataFrame(self.visitas_extraidas)
                return df
            else:
                print("\n⚠️ Nenhuma ficha foi processada")
                return None

        except Exception as e:
            print(f"\n❌ ERRO FATAL: {str(e)}")
            print("🔄 Tentando recuperar...")
            traceback.print_exc()
            return None
        finally:
            if self.browser:
                await self.browser.close()

# Endpoints Flask

@app.route('/')
def index():
    return "Servidor de automação ESUS está rodando!"

@app.route('/start-automation', methods=['POST'])
async def start_automation():
    global current_task
    if current_task and not current_task.done():
        return jsonify({"status": "error", "message": "Uma automação já está em andamento"})

    data = request.json
    url = data.get('url', 'https://esus.saomanuel.sp.gov.br/')
    user = data.get('user')
    password = data.get('password')
    cns = data.get('cns')
    paginas = data.get('paginas', [1])

    if not user or not password or not cns:
        return jsonify({"status": "error", "message": "Parâmetros insuficientes"})

    automation = WebAutomation()
    await automation.setup_browser()
    
    # Executar a automação em uma task assíncrona
    current_task = asyncio.create_task(automation.run_automation(url, user, password, cns, paginas))
    result = await current_task

    if result is not None:
        # Salvar o resultado em um arquivo Excel temporário
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
        result.to_excel(temp_file.name, index=False)
        return send_file(temp_file.name, as_attachment=True, download_name='dados_esus.xlsx')
    else:
        return jsonify({"status": "error", "message": "Falha na automação"})

if __name__ == '__main__':
    app.run(debug=True, port=5000)