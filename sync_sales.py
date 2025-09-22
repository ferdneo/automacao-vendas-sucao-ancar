#!/usr/bin/env python3
"""
Automação Específica - Sucão BOH → Portal Ancar
Baseado na estrutura real dos sistemas
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta
import logging
import requests
from playwright.async_api import async_playwright, TimeoutError
import re

# Configurar logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

class SucaoBOHExtractor:
    """Extrai dados específicos do Sucão BOH"""

    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.base_url = "https://sucao.boh.e-deploy.com.br"

    async def extract_yesterday_sales(self):
        """Extrai vendas do dia anterior seguindo o fluxo exato"""
        yesterday = datetime.now() - timedelta(days=1)
        date_str = yesterday.strftime('%d/%m/%Y')

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()

            try:
                # LOGIN
                logging.info("🔐 Fazendo login no Sucão BOH...")
                await page.goto(f"{self.base_url}/login")
                await page.fill('input[type="email"], input[name="email"]', self.email)
                await page.fill('input[type="password"], input[name="password"]', self.password)
                await page.click('button[type="submit"], input[type="submit"]')
                await page.wait_for_url('**/dashboard*', timeout=30000)
                logging.info("✅ Login realizado com sucesso")

                # NAVEGAR PARA RELATÓRIOS
                logging.info("📊 Acessando relatórios...")
                await page.click('a:has-text("Relatórios"), [href*="reports"]')
                await page.wait_for_load_state('networkidle')

                # EXPANDIR SEÇÃO "Relatórios por dia de negócio" SE NECESSÁRIO E CLICAR NO RELATÓRIO
                relatorios_section = page.locator('text="Relatórios por dia de negócio"')
                if await relatorios_section.is_visible():
                    await relatorios_section.click()
                await page.click('text="Vendas diárias por dia de negócio"')
                await page.wait_for_load_state('networkidle')

                # CLICAR EM "Gerar Relatório"
                logging.info("🗓️ Gerando relatório para ontem...")
                await page.click('button:has-text("Gerar Relatório")')

                # AGUARDAR POPUP E PREENCHER FORMULÁRIO
                await page.wait_for_selector('.modal, .popup')  # Aguarda o popup
                # Selecionar loja via rádio (baseado na imagem: 73 - CONJUNTO NACIONAL - BRASILIA)
                await page.click('input[type="radio"][value*="73"], label:has-text("73 - CONJUNTO NACIONAL - BRASILIA") ~ input[type="radio"]')
                # Preencher datas
                await page.fill('input[name*="data_inicial"], input[placeholder*="Data inicial"]', date_str)
                await page.fill('input[name*="data_final"], input[placeholder*="Data final"]', date_str)
                # Selecionar tipo "Detalhado" (assumindo dropdown)
                await page.select_option('select[name*="tipo"]', label="Detalhado")
                # Clicar em "Enviar"
                await page.click('button:has-text("Enviar")')

                # AGUARDAR ALERTA DE QUE O RELATÓRIO ESTÁ NA FILA (OU FECHAR POPUP)
                try:
                    await page.wait_for_selector('text="Alerta", text="requisitação de geração do relatório"', timeout=10000)
                    logging.info("⏳ Relatório enfileirado...")
                    await page.click('button:has-text("Fechar")')  # Fecha o alerta
                except TimeoutError:
                    pass

                # AGUARDAR O RELATÓRIO APARECER NA TABELA (POLLING SIMPLES)
                for _ in range(10):  # Tenta até 10 vezes ( ~1min)
                    await page.wait_for_timeout(6000)  # Espera 6s por iteração
                    await page.reload()  # Recarrega para atualizar a tabela
                    if await page.locator('table tbody tr').count() > 0:
                        break
                else:
                    raise Exception("Relatório não gerado após espera")

                # SELECIONAR O RÁDIO DO RELATÓRIO MAIS RECENTE (PRIMEIRA LINHA)
                await page.click('table tbody tr:first-child input[type="radio"]')

                # CLICAR EM "Imprimir"
                await page.click('button:has-text("Imprimir")')

                # CAPTURAR NOVA ABA
                async with context.expect_page() as new_page_info:
                    new_page = await new_page_info.value
                await new_page.wait_for_load_state('networkidle')

                # EXTRAIR DADOS DA PÁGINA DO RELATÓRIO
                logging.info("📋 Extraindo dados do relatório...")
                total_liquido_text = await new_page.locator('text="Total Líquido" ~ td, text="R$ 1."').inner_text()  # Ajuste baseado na imagem
                tickets_text = await new_page.locator('td:has-text("Tickets"), tr td:nth-child(2)').inner_text()  # Coluna Tickets

                total_vendas = self.extract_currency(total_liquido_text)
                total_quantidade = self.extract_number(tickets_text)

                if total_vendas == 0 or total_quantidade == 0:
                    raise Exception("Dados não encontrados no relatório")

                sales_data = [{
                    'valor': total_vendas,
                    'quantidade': total_quantidade,
                    'descricao': 'Venda do dia'
                }]

                logging.info(f"✅ Coletadas vendas: R$ {total_vendas:.2f} com {total_quantidade} tickets")

                return sales_data

            except Exception as e:
                logging.error(f"❌ Erro na extração: {e}")
                return []

            finally:
                await browser.close()

    def extract_currency(self, text):
        cleaned = re.sub(r'[^\d,.]', '', text)
        if not cleaned:
            return 0.0
        cleaned = cleaned.replace('.', '').replace(',', '.')
        try:
            return float(cleaned)
        except:
            return 0.0

    def extract_number(self, text):
        numbers = re.findall(r'\d+', text)
        return int(numbers[0]) if numbers else 0

class AncarPortalUpdater:
    """Atualiza dados no Portal Ancar"""
    # (Mantido igual, pois o problema está na extração. Se precisar ajustar seletores aqui, teste os logs)

    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.base_url = "https://vendas.ancarivanhoe.com.br"

    async def update_sales_data(self, sales_data):
        """Atualiza dados de vendas no portal"""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()

            try:
                # LOGIN
                logging.info("🔐 Fazendo login no Portal Ancar...")
                await page.goto(f"{self.base_url}/?Accounts&op=asklogin")
                await page.wait_for_selector('input[name="username"], input[type="text"]')
                await page.fill('input[name="username"], input[type="text"]', self.username)
                await page.fill('input[name="password"], input[type="password"]', self.password)
                await page.click('button:has-text("Entrar"), button[type="submit"]')
                await page.wait_for_load_state('networkidle')
                logging.info("✅ Login no Ancar realizado")

                # NAVEGAR PARA INFORMAR VENDAS
                logging.info("📝 Procurando seção de informar vendas...")
                await page.wait_for_timeout(3000)
                vendas_selectors = [
                    ':has-text("INFORMAR VENDAS")',
                    'button:has-text("Por Digitar"), a:has-text("Por Digitar")',
                    '[href*="vendas"]'
                ]
                for selector in vendas_selectors:
                    if await page.locator(selector).count() > 0:
                        await page.click(selector)
                        await page.wait_for_load_state('networkidle')
                        break

                # PREENCHER O FORMULÁRIO (AJUSTADO PARA CLICAR EM "Por Digitar" SE VISÍVEL)
                if await page.locator('text="Por Digitar"').count() > 0:
                    await page.click('text="Por Digitar"')  # Abre o campo editável para o dia

                await self.fill_sales_form(page, sales_data)

                return True

            except Exception as e:
                logging.error(f"❌ Erro no Portal Ancar: {e}")
                return False

            finally:
                await browser.close()

    async def fill_sales_form(self, page, sales_data):
        """Preenche formulário de vendas"""
        total_vendas = sum(item['valor'] for item in sales_data)
        total_quantidade = sum(item['quantidade'] for item in sales_data)

        logging.info(f"💰 Preenchendo: R$ {total_vendas:.2f} - {total_quantidade} tickets")

        # Data de ontem (já deve estar selecionada via "Por Digitar")
        yesterday = (datetime.now() - timedelta(days=1)).strftime('%d/%m/%Y')

        form_selectors = {
            'vendas': ['input[name*="venda"], input[placeholder*="venda"], input[type="number"]'],
            'tickets': ['input[name*="ticket"], input[name*="atendimento"], input[placeholder*="ticket"]'],
            'data': ['input[name*="data"], input[type="date"], input[placeholder*="data"]']
        }

        # Preencher vendas
        for selector in form_selectors['vendas']:
            if await page.locator(selector).count() > 0:
                await page.fill(selector, f"{total_vendas:.2f}".replace('.', ','))
                break

        # Preencher tickets
        for selector in form_selectors['tickets']:
            if await page.locator(selector).count() > 0:
                await page.fill(selector, str(total_quantidade))
                break

        # Preencher data se necessário
        for selector in form_selectors['data']:
            if await page.locator(selector).count() > 0:
                await page.fill(selector, yesterday)
                break

        # Salvar
        save_buttons = [
            'button:has-text("Salvar"), button:has-text("Enviar"), button:has-text("Confirmar"), button[type="submit"]'
        ]
        for selector in save_buttons:
            if await page.locator(selector).count() > 0:
                await page.click(selector)
                await page.wait_for_load_state('networkidle')
                break

        logging.info("✅ Dados preenchidos no Portal Ancar")

class TelegramReporter:
    """Envia relatórios via Telegram"""
    # (Mantido igual)

    def __init__(self, bot_token, chat_id):
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send_daily_report(self, sales_data, success):
        total_vendas = sum(item['valor'] for item in sales_data)
        total_itens = len(sales_data)

        emoji = "✅" if success else "❌"
        status = "Sucesso" if success else "Falha"

        message = f"""
{emoji} **Relatório Automação - {datetime.now().strftime('%d/%m/%Y')}**
💰 **Vendas Coletadas (Sucão BOH):**
• Valor Total: R$ {total_vendas:.2f}
• Itens: {total_itens}
📊 **Status Preenchimento (Portal Ancar):**
• {status}
🕐 **Próxima execução:** Amanhã às 8:00 AM
---
*Sistema de Automação Sucão → Ancar*
        """.strip()

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        data = {
            'chat_id': self.chat_id,
            'text': message,
            'parse_mode': 'Markdown'
        }

        response = requests.post(url, data=data)

        if response.status_code == 200:
            logging.info("📱 Relatório enviado via Telegram")
        else:
            logging.error(f"❌ Erro no Telegram: {response.text}")

async def main():
    # (Mantido igual, mas agora com extração corrigida deve preencher certo)

    logging.info("🚀 Iniciando automação Sucão → Ancar")

    required_vars = [
        'SUCAO_EMAIL', 'SUCAO_PASSWORD',
        'ANCAR_USERNAME', 'ANCAR_PASSWORD',
        'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID'
    ]

    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        logging.error(f"❌ Variáveis não configuradas: {missing_vars}")
        return

    try:
        extractor = SucaoBOHExtractor(
            os.getenv('SUCAO_EMAIL'),
            os.getenv('SUCAO_PASSWORD')
        )
        sales_data = await extractor.extract_yesterday_sales()

        if not sales_data:
            logging.warning("⚠️ Nenhum dado coletado do Sucão BOH")

        updater = AncarPortalUpdater(
            os.getenv('ANCAR_USERNAME'),
            os.getenv('ANCAR_PASSWORD')
        )
        success = await updater.update_sales_data(sales_data)

        reporter = TelegramReporter(
            os.getenv('TELEGRAM_BOT_TOKEN'),
            os.getenv('TELEGRAM_CHAT_ID')
        )
        reporter.send_daily_report(sales_data, success)

        if success:
            logging.info("🎉 Automação concluída com sucesso!")
        else:
            logging.warning("⚠️ Automação concluída com problemas")

    except Exception as e:
        logging.error(f"💥 Erro crítico na automação: {e}")

        try:
            reporter = TelegramReporter(
                os.getenv('TELEGRAM_BOT_TOKEN'),
                os.getenv('TELEGRAM_CHAT_ID')
            )
            reporter.send_daily_report([], False)
        except:
            pass

if __name__ == "__main__":
    asyncio.run(main())
