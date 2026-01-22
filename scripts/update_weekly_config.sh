#!/bin/bash
# Weekly Config Update Script for Frontend Container
# 用于在frontend容器中每周更新hourly配置文件
# 挂载点: /mnt/efs/configs/ -> EFS:/ai-trader/configs/

set -e

# ============================================
# 配置参数
# ============================================
# 配置文件路径（frontend容器中的挂载点）
CONFIG_DIR="${CONFIG_DIR:-/mnt/efs/configs}"
JSON_FILE="$CONFIG_DIR/astock_config_hourly.json"
YAML_FILE="${YAML_DIR:-/mnt/efs/logs}/docs/config.yaml"

# 日志配置
LOG_DIR="${LOG_DIR:-/mnt/efs/logs}/scheduler"
LOG_FILE="$LOG_DIR/weekly_update_$(date +%Y%m%d_%H%M%S).log"

# 创建日志目录
mkdir -p "$LOG_DIR" 2>/dev/null || true

# ============================================
# 日志函数
# ============================================
log() {
    local level="$1"
    local message="$2"
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] [$level] $message" | tee -a "$LOG_FILE"
}

log_info() {
    log "INFO" "$1"
}

log_success() {
    log "SUCCESS" "$1"
}

log_error() {
    log "ERROR" "$1"
}

# ============================================
# 检查前置条件
# ============================================
check_prerequisites() {
    log_info "检查前置条件..."
    
    # 检查 jq 是否安装
    if ! command -v jq &> /dev/null; then
        log_error "jq 未安装，无法解析JSON配置文件"
        exit 1
    fi
    
    # 检查配置文件是否存在
    if [ ! -f "$JSON_FILE" ]; then
        log_error "配置文件不存在: $JSON_FILE"
        exit 1
    fi
    
    # 检查配置文件是否可写
    if [ ! -w "$JSON_FILE" ]; then
        log_error "配置文件不可写: $JSON_FILE"
        log_error "请确保EFS挂载为可写模式"
        exit 1
    fi
    
    log_success "前置条件检查通过"
}

# ============================================
# 更新配置文件中的日期
# ============================================
update_config_dates() {
    log_info "=========================================="
    log_info "更新配置文件日期"
    log_info "=========================================="
    
    # 计算时间
    local TODAY=$(date +%Y-%m-%d' '%H:%M:%S)
    local TODAY_30AFTER=$(date -d "+30 minutes" '+%Y-%m-%d %H:%M:%S')
    local TODAY_DATE=$(date +%y%m%d)
    
    log_info "当前时间: $TODAY"
    log_info "结束时间: $TODAY_30AFTER"
    log_info "日期标识: $TODAY_DATE"
    
    # 备份原配置文件到logs目录（避免EFS configs目录权限问题）
    local BACKUP_DIR="$LOG_DIR/config_backups"
    mkdir -p "$BACKUP_DIR" 2>/dev/null || true
    local BACKUP_FILE="$BACKUP_DIR/astock_config_hourly.json.backup_$(date +%Y%m%d_%H%M%S)"
    cp "$JSON_FILE" "$BACKUP_FILE"
    log_info "已备份配置文件: $BACKUP_FILE"
    
    # 创建临时工作目录（用于jq生成临时文件）
    local TMP_DIR="$LOG_DIR/tmp"
    mkdir -p "$TMP_DIR" 2>/dev/null || true
    local TMP_FILE="$TMP_DIR/config_update_tmp.json"
    
    # 更新 init_date
    jq --arg date "$TODAY" '.date_range.init_date = $date' "$JSON_FILE" > "$TMP_FILE" && cat "$TMP_FILE" > "$JSON_FILE"
    log_success "更新 init_date = $TODAY"
    
    # 更新 end_date
    jq --arg date "$TODAY_30AFTER" '.date_range.end_date = $date' "$JSON_FILE" > "$TMP_FILE" && cat "$TMP_FILE" > "$JSON_FILE"
    log_success "更新 end_date = $TODAY_30AFTER"
    
    # 更新 models 中的 name（替换日期后缀）
    jq --arg today "$TODAY_DATE" '
      .models |= map(
        .name |= sub("_[0-9]{6}$"; "_\($today)")
      )
    ' "$JSON_FILE" > "$TMP_FILE" && cat "$TMP_FILE" > "$JSON_FILE"
    log_success "更新 models[].name 日期后缀为 _$TODAY_DATE"
    
    # 更新 models 中的 signature（替换日期后缀）
    jq --arg today "$TODAY_DATE" '
      .models |= map(
        .signature |= sub("_[0-9]{6}$"; "_\($today)")
      )
    ' "$JSON_FILE" > "$TMP_FILE" && cat "$TMP_FILE" > "$JSON_FILE"
    log_success "更新 models[].signature 日期后缀为 _$TODAY_DATE"
    
    # 清理临时文件
    rm -f "$TMP_FILE"
    
    # 显示更新后的配置（仅关键字段）
    log_info "=========================================="
    log_info "更新后的配置（关键字段）："
    log_info "=========================================="
    
    local INIT_DATE_VALUE=$(jq -r '.date_range.init_date' "$JSON_FILE")
    local END_DATE_VALUE=$(jq -r '.date_range.end_date' "$JSON_FILE")
    log_info "  init_date: $INIT_DATE_VALUE"
    log_info "  end_date: $END_DATE_VALUE"
    
    log_info "  models:"
    jq -r '.models[] | "    - name: \(.name), signature: \(.signature), enabled: \(.enabled)"' "$JSON_FILE" | while IFS= read -r line; do
        log_info "$line"
    done
}

# ============================================
# 更新 YAML 配置文件（如果存在）
# ============================================
update_yaml_config() {
    if [ ! -f "$YAML_FILE" ]; then
        log_info "YAML配置文件不存在，跳过: $YAML_FILE"
        return 0
    fi
    
    log_info "=========================================="
    log_info "更新YAML配置文件"
    log_info "=========================================="
    
    local TODAY_DATE=$(date +%y%m%d)
    
    # 备份YAML文件到logs目录
    local BACKUP_DIR="$LOG_DIR/config_backups"
    mkdir -p "$BACKUP_DIR" 2>/dev/null || true
    local BACKUP_FILE="$BACKUP_DIR/config.yaml.backup_$(date +%Y%m%d_%H%M%S)"
    cp "$YAML_FILE" "$BACKUP_FILE"
    log_info "已备份YAML文件: $BACKUP_FILE"
    
    # 创建临时工作目录
    local TMP_DIR="$LOG_DIR/tmp"
    mkdir -p "$TMP_DIR" 2>/dev/null || true
    local TMP_FILE="$TMP_DIR/config_yaml_tmp.yaml"
    
    # 替换日期后缀（精确匹配 folder 和 display_name 行）
    sed -E "s/(_[0-9]{6})([\"'\` ]*$)/_$TODAY_DATE\2/g" "$YAML_FILE" > "$TMP_FILE" && cat "$TMP_FILE" > "$YAML_FILE"
    log_success "YAML配置文件已更新"
    
    # 清理临时文件
    rm -f "$TMP_FILE"
}

# ============================================
# 清理旧备份文件（保留最近7天）
# ============================================
cleanup_old_backups() {
    log_info "=========================================="
    log_info "清理旧备份文件（保留7天）"
    log_info "=========================================="
    
    # 清理备份文件（统一在logs目录下）
    local BACKUP_DIR="$LOG_DIR/config_backups"
    if [ -d "$BACKUP_DIR" ]; then
        find "$BACKUP_DIR" -name "*.backup_*" -mtime +7 -type f -delete 2>/dev/null || true
        local BACKUP_COUNT=$(find "$BACKUP_DIR" -name "*.backup_*" -type f 2>/dev/null | wc -l)
        log_info "配置备份文件剩余: $BACKUP_COUNT 个"
    fi
    
    # 清理旧日志（保留30天）
    find "$LOG_DIR" -name "weekly_update_*.log" -mtime +30 -type f -delete 2>/dev/null || true
    local LOG_COUNT=$(find "$LOG_DIR" -name "weekly_update_*.log" -type f | wc -l)
    log_info "日志文件剩余: $LOG_COUNT 个"
}

# ============================================
# 主函数
# ============================================
main() {
    log_info "=========================================="
    log_info "每周配置更新脚本"
    log_info "=========================================="
    log_info "配置文件: $JSON_FILE"
    log_info "YAML文件: $YAML_FILE"
    log_info "日志文件: $LOG_FILE"
    log_info ""
    
    # 检查前置条件
    check_prerequisites
    
    # 更新配置日期
    update_config_dates
    
    # 更新YAML配置（可选）
    update_yaml_config
    
    # 清理旧备份
    cleanup_old_backups
    
    log_info ""
    log_success "=========================================="
    log_success "配置更新完成！"
    log_success "=========================================="
    
    # 显示下一步操作提示
    log_info ""
    log_info "下一步操作："
    log_info "  1. 运行 aws_ecs_run_all.sh 启动交易任务"
    log_info "  2. 或手动调用 ECS API 启动任务"
    log_info ""
}

# 执行主函数
main "$@"
