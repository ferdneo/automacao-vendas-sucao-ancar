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
from playwright.async_api import async_playwright
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
        """Extrai vendas do dia anterior"""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            
            try:
                # LOGIN
                logging.info("🔐 Fazendo login no Sucão BOH...")
                await page.goto(f"{self.base_url}/login")
                
                # Preencher credenciais
                await page.fill('input[type="email"], input[name="email"]', self.email)
                await page.fill('input[type="password"], input[name="password"]', self.password)
                await page.click('button[type="submit"], input[type="submit"]')
                
                # Aguardar dashboard
                await page.wait_for_url('**/dashboard*', timeout=30000)
                logging.info("✅ Login realizado com sucesso")
                
                # NAVEGAR PARA RELATÓRIOS
                logging.info("📊 Acessando relatórios...")
                
                # Clicar em "Relatórios" no menu lateral
                await page.click('a:has-text("Relatórios"), [href*="reports"]')
                await page.wait_for_load_state('networkidle')
                
                # Expandir seção "Vendas" se necessário
                vendas_section = page.locator('text="Vendas"').first
                if await vendas_section.count() > 0:
                    await vendas_section.click()
                
                # Clicar em "Relatório Geral de Vendas"
                await page.click('a:has-text("Relatório Geral de Vendas"), a:has-text("Vendas por dia")')
                await page.wait_for_load_state('networkidle')
                
                # FILTRAR POR DATA DE ONTEM
                yesterday = datetime.now() - timedelta(days=1)
                date_str = yesterday.strftime('%d/%m/%Y')
                
                logging.info(f"🗓️ Filtrando por data: {date_str}")
                
                # Procurar campos de data
                date_inputs = [
                    'input[name*="data"]',
                    'input[type="date"]',
                    'input[placeholder*="data"]'
                ]
                
                for selector in date_inputs:
                    if await page.locator(selector).count() > 0:
                        await page.fill(selector, date_str)
                        break
                
                # Clicar em buscar/filtrar
                await page.click('button:has-text("Buscar"), button:has-text("Filtrar"), button:has-text("Consultar")')
                await page.wait_for_load_state('networkidle')
                
                # EXTRAIR DADOS DA TABELA
                logging.info("📋 Extraindo dados de vendas...")
                
                sales_data = []
                
                # Procurar tabela de resultados
                table_rows = await page.locator('table tbody tr, .table-row').all()
                
                for row in table_rows:
                    try:
                        row_text = await row.inner_text()
                        cells = await row.locator('td, .cell').all()
                        
                        if len(cells) >= 2:
                            # Extrair valor e outros dados
                            valor_text = await cells[0].inner_text() if cells else row_text
                            quantidade_text = await cells[1].inner_text() if len(cells) > 1 else "1"
                            
                            valor = self.extract_currency(valor_text)
                            quantidade = self.extract_number(quantidade_text)
                            
                            if valor > 0:  # Só adicionar se tem valor
                                sales_data.append({
                                    'valor': valor,
                                    'quantidade': quantidade,
                                    'descricao': row_text[:50]  # Primeiros 50 caracteres
                                })
                    
                    except Exception as e:
                        logging.warning(f"Erro ao processar linha: {e}")
                        continue
                
                logging.info(f"✅ Coletadas {len(sales_data)} vendas")
                
                # Se não encontrou dados na tabela, tentar outras abordagens
                if not sales_data:
                    # Procurar por totais ou resumos
                    total_elements = await page.locator(':has-text("Total"), :has-text("R$")').all()
                    for element in total_elements:
                        text = await element.inner_text()
                        valor = self.extract_currency(text)
                        if valor > 0:
                            sales_data.append({
                                'valor': valor,
                                'quantidade': 1,
                                'descricao': 'Venda do dia'
                            })
                            break
                
                return sales_data
                
            except Exception as e:
                logging.error(f"❌ Erro na extração: {e}")
                return []
            
            finally:
                await browser.close()
    
    def extract_currency(self, text):
        """Extrai valor monetário do texto"""
        # Remove tudo exceto números, vírgula e ponto
        cleaned = re.sub(r'[^\d,.]', '', text)
        
        if not cleaned:
            return 0.0
        
        # Tratar formato brasileiro (1.234,56)
        if ',' in cleaned and '.' in cleaned:
            # Formato: 1.234,56
            cleaned = cleaned.replace('.', '').replace(',', '.')
        elif ',' in cleaned:
            # Formato: 1234,56
            cleaned = cleaned.replace(',', '.')
        
        try:
            return float(cleaned)
        except:
            return 0.0
    
    def extract_number(self, text):
        """Extrai número inteiro do texto"""
        numbers = re.findall(r'\d+', text)
        return int(numbers[0]) if numbers else 1


class AncarPortalUpdater:
    """Atualiza dados no Portal Ancar"""
    
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
                # LOGIN NO PORTAL ANCAR
                logging.info("🔐 Fazendo login no Portal Ancar...")
                await page.goto(f"{self.base_url}/?Accounts&op=asklogin")
                
                # Aguardar formulário aparecer
                await page.wait_for_selector('input[name="username"], input[name="email"], input[type="text"]')
                
                # Preencher credenciais
                await page.fill('input[name="username"], input[name="email"], input[type="text"]', self.username)
                await page.fill('input[name="password"], input[type="password"]', self.password)
                
                # Fazer login
                await page.click('button[type="submit"], input[type="submit"], button:has-text("Entrar")')
                await page.wait_for_load_state('networkidle')
                
                logging.info("✅ Login no Ancar realizado")
                
                # PROCURAR SEÇÃO DE INFORMAR VENDAS
                logging.info("📝 Procurando formulário de vendas...")
                
                # Aguardar página carregar completamente
                await page.wait_for_timeout(3000)
                
                # Procurar por elementos relacionados a vendas
                vendas_selectors = [
                    ':has-text("INFORMAR VENDAS")',
                    ':has-text("Por Digitar")',
                    'button:has-text("Por Digitar")',
                    'a:has-text("Vendas")',
                    '[href*="vendas"]'
                ]
                
                vendas_found = False
                for selector in vendas_selectors:
                    if await page.locator(selector).count() > 0:
                        await page.click(selector)
                        await page.wait_for_load_state('networkidle')
                        vendas_found = True
                        break
                
                if not vendas_found:
                    logging.warning("⚠️ Seção de vendas não encontrada automaticamente")
                    # Tentar navegar manualmente por links/menus
                
                # PREENCHER DADOS DE VENDAS
                await self.fill_sales_form(page, sales_data)
                
                return True
                
            except Exception as e:
                logging.error(f"❌ Erro no Portal Ancar: {e}")
                return False
            
            finally:
                await browser.close()
    
    async def fill_sales_form(self, page, sales_data):
        """Preenche formulário de vendas"""
        try:
            # Calcular totais
            total_vendas = sum(item['valor'] for item in sales_data)
            total_quantidade = sum(item['quantidade'] for item in sales_data)
            
            logging.info(f"💰 Preenchendo: R$ {total_vendas:.2f} - {total_quantidade} itens")
            
            # Data de ontem
            yesterday = (datetime.now() - timedelta(days=1)).strftime('%d/%m/%Y')
            
            # Procurar campos do formulário
            form_selectors = {
                'vendas': [
                    'input[name*="venda"]',
                    'input[name*="valor"]',
                    'input[placeholder*="venda"]',
                    'input[type="number"]'
                ],
                'tickets': [
                    'input[name*="ticket"]',
                    'input[name*="atendimento"]',
                    'input[placeholder*="ticket"]'
                ],
                'data': [
                    'input[name*="data"]',
                    'input[type="date"]',
                    'input[placeholder*="data"]'
                ]
            }
            
            # Preencher campo de vendas
            for selector in form_selectors['vendas']:
                if await page.locator(selector).count() > 0:
                    await page.fill(selector, f"{total_vendas:.2f}".replace('.', ','))
                    break
            
            # Preencher campo de tickets (usando quantidade)
            for selector in form_selectors['tickets']:
                if await page.locator(selector).count() > 0:
                    await page.fill(selector, str(total_quantidade))
                    break
            
            # Preencher data
            for selector in form_selectors['data']:
                if await page.locator(selector).count() > 0:
                    await page.fill(selector, yesterday)
                    break
            
            # Procurar e clicar em botão de salvar
            save_buttons = [
                'button:has-text("Salvar")',
                'button:has-text("Enviar")',
                'button:has-text("Confirmar")',
                'input[type="submit"]',
                'button[type="submit"]'
            ]
            
            for selector in save_buttons:
                if await page.locator(selector).count() > 0:
                    await page.click(selector)
                    await page.wait_for_load_state('networkidle')
                    break
            
            logging.info("✅ Dados preenchidos no Portal Ancar")
            
        except Exception as e:
            logging.error(f"❌ Erro ao preencher formulário: {e}")
            raise


class TelegramReporter:
    """Envia relatórios via Telegram"""
    
    def __init__(self, bot_token, chat_id):
        self.bot_token = bot_token
        self.chat_id = chat_id
    
    def send_daily_report(self, sales_data, success):
        """Envia relatório diário"""
        try:
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
                
        except Exception as e:
            logging.error(f"❌ Erro ao enviar Telegram: {e}")


async def main():
    """Função principal da automação"""
    
    logging.info("🚀 Iniciando automação Sucão → Ancar")
    
    # Verificar configurações
    required_vars = [
        'SUCAO_EMAIL', 'SUCAO_PASSWORD',
        'ANCAR_USERNAME', 'ANCAR_PASSWORD',
        'TELEGRAM_BOT_TOKEN', 'TELEGRAM_CHAT_ID'
    ]
    
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logging.error(f"❌ Variáveis não configuradas: {missing_vars}")
        print("❌ Faltam configurar estas senhas:")
        for var in missing_vars:
            print(f"   - {var}")
        return
    
    try:
        # 1. EXTRAIR DADOS DO SUCÃO BOH
        logging.info("📊 Coletando dados do Sucão BOH...")
        extractor = SucaoBOHExtractor(
            os.getenv('SUCAO_EMAIL'),
            os.getenv('SUCAO_PASSWORD')
        )
        
        sales_data = await extractor.extract_yesterday_sales()
        
        if not sales_data:
            logging.warning("⚠️ Nenhum dado coletado do Sucão BOH")
        
        # 2. ATUALIZAR PORTAL ANCAR
        logging.info("📝 Atualizando Portal Ancar...")
        updater = AncarPortalUpdater(
            os.getenv('ANCAR_USERNAME'),
            os.getenv('ANCAR_PASSWORD')
        )
        
        success = await updater.update_sales_data(sales_data)
        
        # 3. ENVIAR RELATÓRIO
        logging.info("📱 Enviando relatório...")
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
        
        # Enviar erro via Telegram
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
