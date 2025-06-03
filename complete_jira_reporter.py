#!/usr/bin/env python3
"""
Relatório COMPLETO Sprint SQHUB → Discord
Executa via GitHub Actions diariamente
"""

import requests
import json
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import statistics
import os

# Configurações
JIRA_URL = "https://everinbox.atlassian.net"
JIRA_EMAIL = os.getenv('JIRA_EMAIL')
JIRA_TOKEN = os.getenv('JIRA_TOKEN')
DISCORD_WEBHOOK = os.getenv('DISCORD_WEBHOOK')

def get_sprint_issues():
    """Busca todas as issues do sprint atual"""
    jql = "project = SQHUB AND Sprint in openSprints()"
    
    response = requests.get(
        f"{JIRA_URL}/rest/api/3/search",
        params={
            'jql': jql,
            'fields': 'key,summary,status,assignee,priority,created,updated,timetracking,changelog',
            'maxResults': 200,
            'expand': 'changelog'
        },
        auth=(JIRA_EMAIL, JIRA_TOKEN)
    )
    
    return response.json()['issues'] if response.status_code == 200 else []

def analyze_sprint_data(issues):
    """Análise completa dos dados do sprint"""
    
    # Contadores básicos
    status_count = Counter()
    dev_workload = Counter()
    priority_count = Counter()
    issue_types = Counter()
    
    # Métricas avançadas  
    dev_completed = defaultdict(int)
    dev_in_progress = defaultdict(int)
    time_in_status = defaultdict(list)
    recent_completions = []
    blocked_issues = []
    unassigned_issues = []
    
    today = datetime.now()
    yesterday = today - timedelta(days=1)
    
    for issue in issues:
        key = issue['key']
        fields = issue['fields']
        
        # Contadores básicos
        status = fields['status']['name']
        assignee = fields['assignee']['displayName'] if fields['assignee'] else 'Não atribuído'
        priority = fields['priority']['name']
        
        status_count[status] += 1
        dev_workload[assignee] += 1
        priority_count[priority] += 1
        issue_types[fields['issuetype']['name']] += 1
        
        # Análises por desenvolvedor
        if fields['assignee']:
            if status == 'Done':
                dev_completed[assignee] += 1
            elif status == 'EM ANDAMENTO':
                dev_in_progress[assignee] += 1
        else:
            unassigned_issues.append({
                'key': key,
                'summary': fields['summary'][:50] + '...',
                'status': status
            })
            
        # Issues bloqueadas
        if 'IMPEDIMENTO' in status.upper() or 'BLOCKED' in status.upper():
            blocked_issues.append({
                'key': key,
                'summary': fields['summary'][:50] + '...',
                'assignee': assignee,
                'days_blocked': (today - datetime.fromisoformat(fields['updated'].replace('Z', '+00:00').replace('+00:00', ''))).days
            })
            
        # Conclusões recentes
        updated = datetime.fromisoformat(fields['updated'].replace('Z', '+00:00').replace('+00:00', ''))
        if status == 'Done' and updated >= yesterday:
            recent_completions.append({
                'key': key,
                'summary': fields['summary'][:40] + '...',
                'assignee': assignee,
                'completed_date': updated.strftime('%d/%m %H:%M')
            })
    
    # Cálculos de progresso
    total_issues = len(issues)
    completed_issues = status_count.get('Done', 0)
    progress_percent = round((completed_issues / total_issues * 100), 1) if total_issues > 0 else 0
    
    # Estimativa de conclusão (baseada no ritmo atual)
    if len(recent_completions) > 0:
        daily_completion_rate = len([c for c in recent_completions if 
                                   datetime.strptime(c['completed_date'], '%d/%m %H:%M').date() == yesterday.date()])
        remaining_issues = total_issues - completed_issues
        estimated_days = round(remaining_issues / max(daily_completion_rate, 1))
    else:
        estimated_days = "Não calculado"
    
    return {
        'total_issues': total_issues,
        'completed_issues': completed_issues,
        'progress_percent': progress_percent,
        'status_count': dict(status_count),
        'dev_workload': dict(dev_workload),
        'dev_completed': dict(dev_completed),
        'dev_in_progress': dict(dev_in_progress),
        'priority_count': dict(priority_count),
        'issue_types': dict(issue_types),
        'recent_completions': recent_completions,
        'blocked_issues': blocked_issues,
        'unassigned_issues': unassigned_issues,
        'estimated_days': estimated_days
    }

def create_discord_message(analysis):
    """Cria mensagem completa para o Discord"""
    
    def get_status_emoji(status):
        emojis = {
            'A FAZER': '📋', 'TODO': '📋',
            'EM ANDAMENTO': '🔄', 'IN PROGRESS': '🔄',
            'EM REVISÃO': '👀', 'IN REVIEW': '👀',
            'AGUARDANDO DEPLOY': '⏳', 'WAITING': '⏳',
            'Done': '✅', 'CONCLUÍDO': '✅',
            'IMPEDIMENTO': '🚫', 'BLOCKED': '🚫'
        }
        return emojis.get(status, '📌')
    
    def get_priority_emoji(priority):
        emojis = {
            'Highest': '🔴', 'High': '🟠', 
            'Medium': '🟡', 'Low': '🟢', 'Lowest': '⚪'
        }
        return emojis.get(priority, '⚪')
    
    # Header com resumo executivo
    message = f"""📊 **RELATÓRIO COMPLETO - SPRINT SQHUB**
📅 {datetime.now().strftime('%d/%m/%Y às %H:%M')} | 🚀 **Sprint Ativo**

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**📈 RESUMO EXECUTIVO**
🎯 **{analysis['total_issues']} tarefas** no sprint atual
✅ **{analysis['completed_issues']} concluídas** ({analysis['progress_percent']}%)
⏰ **{analysis['total_issues'] - analysis['completed_issues']} restantes**
📊 **Previsão:** {analysis['estimated_days']} dias para conclusão

**📋 DISTRIBUIÇÃO POR STATUS**"""
    
    for status, count in analysis['status_count'].items():
        emoji = get_status_emoji(status)
        percentage = round((count / analysis['total_issues']) * 100, 1)
        message += f"\n{emoji} **{status}**: {count} tarefas ({percentage}%)"
    
    message += f"""

**👥 PERFORMANCE POR DESENVOLVEDOR**"""
    
    for dev, total in analysis['dev_workload'].items():
        completed = analysis['dev_completed'].get(dev, 0)
        in_progress = analysis['dev_in_progress'].get(dev, 0)
        completion_rate = round((completed / total) * 100, 1) if total > 0 else 0
        
        message += f"""
👨‍💻 **{dev}**:
  • Total: {total} tarefas | ✅ {completed} concluídas ({completion_rate}%)
  • 🔄 {in_progress} em andamento | 📋 {total - completed - in_progress} pendentes"""
    
    # Conclusões recentes (últimas 24h)
    if analysis['recent_completions']:
        message += f"""

**🎉 CONCLUSÕES RECENTES (últimas 24h)**"""
        for completion in analysis['recent_completions'][:5]:
            message += f"\n✅ **{completion['key']}** - {completion['summary']}"
            message += f"\n  👤 {completion['assignee']} | 📅 {completion['completed_date']}"
        
        if len(analysis['recent_completions']) > 5:
            message += f"\n... e mais {len(analysis['recent_completions']) - 5} tarefas"
    else:
        message += f"""

**📊 CONCLUSÕES RECENTES**
ℹ️ Nenhuma tarefa foi concluída nas últimas 24 horas"""
    
    # Impedimentos ativos
    if analysis['blocked_issues']:
        message += f"""

**🚨 IMPEDIMENTOS CRÍTICOS ({len(analysis['blocked_issues'])})**"""
        for blocked in analysis['blocked_issues']:
            message += f"\n⛔ **{blocked['key']}** - {blocked['summary']}"
            message += f"\n  👤 {blocked['assignee']} | 📅 {blocked['days_blocked']} dias bloqueado"
    else:
        message += f"""

**✅ IMPEDIMENTOS**
🎉 Nenhum impedimento ativo no momento!"""
    
    # Tarefas sem responsável
    if analysis['unassigned_issues']:
        message += f"""

**⚠️ TAREFAS SEM RESPONSÁVEL ({len(analysis['unassigned_issues'])})**"""
        for unassigned in analysis['unassigned_issues'][:3]:
            message += f"\n🔴 **{unassigned['key']}** - {unassigned['summary']}"
        
        if len(analysis['unassigned_issues']) > 3:
            message += f"\n... e mais {len(analysis['unassigned_issues']) - 3} tarefas"
    
    # Métricas por prioridade
    message += f"""

**⚡ DISTRIBUIÇÃO POR PRIORIDADE**"""
    for priority, count in analysis['priority_count'].items():
        emoji = get_priority_emoji(priority)
        message += f"\n{emoji} **{priority}**: {count} tarefas"
    
    # Tipos de issue
    message += f"""

**🏷️ TIPOS DE TAREFA**"""
    for issue_type, count in analysis['issue_types'].items():
        message += f"\n• **{issue_type}**: {count} tarefas"
    
    # Footer com próximas ações
    message += f"""

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 **PRÓXIMAS AÇÕES RECOMENDADAS:**"""
    
    if analysis['unassigned_issues']:
        message += f"\n• ⚠️ Atribuir responsáveis para {len(analysis['unassigned_issues'])} tarefas"
    
    if analysis['blocked_issues']:
        message += f"\n• 🚨 Resolver {len(analysis['blocked_issues'])} impedimentos ativos"
    
    if analysis['progress_percent'] < 50:
        message += f"\n• ⚡ Acelerar desenvolvimento - progresso abaixo de 50%"
    
    message += f"""

🤖 **Relatório Automático** | 📊 Dados em tempo real
🔄 Próxima atualização: {(datetime.now() + timedelta(days=1)).strftime('%d/%m às %H:%M')}"""
    
    return message

def send_to_discord(message):
    """Envia mensagem para o Discord"""
    
    # Limitar tamanho da mensagem (Discord tem limite de 2000 caracteres)
    if len(message) > 1900:
        # Dividir em múltiplas mensagens se necessário
        parts = [message[i:i+1900] for i in range(0, len(message), 1900)]
        
        for i, part in enumerate(parts):
            if i > 0:
                part = f"**[Continuação {i+1}]**\n\n" + part
            
            response = requests.post(DISCORD_WEBHOOK, json={'content': part})
            
            if response.status_code != 204:
                print(f"Erro ao enviar parte {i+1}: {response.status_code}")
                return False
        
        return True
    else:
        response = requests.post(DISCORD_WEBHOOK, json={'content': message})
        return response.status_code == 204

def main():
    """Função principal"""
    print("🔄 Iniciando relatório completo SQHUB...")
    
    # Buscar issues do sprint
    print("📊 Coletando dados do Jira...")
    issues = get_sprint_issues()
    
    if not issues:
        print("❌ Nenhuma issue encontrada!")
        return
        
    print(f"✅ {len(issues)} issues encontradas")
    
    # Analisar dados
    print("🧮 Analisando dados...")
    analysis = analyze_sprint_data(issues)
    
    # Criar mensagem
    print("📝 Gerando relatório...")
    message = create_discord_message(analysis)
    
    # Enviar para Discord
    print("📤 Enviando para Discord...")
    success = send_to_discord(message)
    
    if success:
        print("✅ Relatório enviado com sucesso!")
        print(f"📊 Resumo: {analysis['total_issues']} tarefas, {analysis['progress_percent']}% concluído")
    else:
        print("❌ Falha ao enviar relatório!")

if __name__ == "__main__":
    main()
