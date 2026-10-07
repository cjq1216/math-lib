"""系统备份与恢复 CLI 工具。

支持以下运维操作：
  python -m app.cli.backup create [--description "说明"]
  python -m app.cli.backup list
  python -m app.cli.backup restore <filename> [--confirm]
  python -m app.cli.backup cleanup
"""

import argparse
import sys

from app.services.backup_service import (
    cleanup_old_backups,
    create_backup,
    list_backups,
    restore_from_backup,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="初中数学题库系统备份与恢复命令行工具")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # create
    create_parser = subparsers.add_parser("create", help="创建新备份")
    create_parser.add_argument("--description", "-d", type=str, default=None, help="备份描述信息")

    # list
    subparsers.add_parser("list", help="列出所有可用备份")

    # restore
    restore_parser = subparsers.add_parser("restore", help="从备份文件恢复数据")
    restore_parser.add_argument("filename", type=str, help="待恢复的备份文件名 (如 math_bank_backup_xxx.zip)")
    restore_parser.add_argument(
        "--confirm",
        action="store_true",
        help="确认覆盖现有数据库与媒体文件",
    )

    # cleanup
    subparsers.add_parser("cleanup", help="执行保留策略清理过期备份")

    args = parser.parse_args()

    if args.command == "create":
        print("正在创建系统数据与媒体完整备份...")
        try:
            item = create_backup(description=args.description)
            print("备份成功！")
            print(f"文件名: {item.filename}")
            print(f"ID: {item.backup_id}")
            print(f"大小: {item.size_bytes} 字节")
            print(f"数据库 SHA256: {item.database_sha256}")
            print(f"媒体文件数: {item.media_file_count}")
        except Exception as e:
            print(f"备份失败: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "list":
        items = list_backups()
        if not items:
            print("当前未发现任何备份。")
            return
        print(f"共发现 {len(items)} 个备份：")
        print(f"{'文件名':<45} | {'大小(KB)':<10} | {'时间':<20} | {'状态'}")
        print("-" * 90)
        for it in items:
            size_kb = round(it.size_bytes / 1024, 1)
            print(f"{it.filename:<45} | {size_kb:<10} | {it.created_at[:19]:<20} | {it.status}")

    elif args.command == "restore":
        if not args.confirm:
            print("错误：恢复操作将覆盖现有数据库与媒体文件！请指定 --confirm 参数确认执行。", file=sys.stderr)
            sys.exit(1)
        print(f"正在准备从 {args.filename} 恢复数据...")
        try:
            res = restore_from_backup(args.filename)
            print("数据恢复成功！")
            print(f"恢复时间: {res.restored_at}")
            print(f"恢复前快照: {res.pre_restore_backup or '无'}")
            print(f"媒体文件数: {res.media_file_count}")
        except Exception as e:
            print(f"恢复失败: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "cleanup":
        print("正在执行保留策略清理...")
        deleted = cleanup_old_backups()
        print(f"已清理 {len(deleted)} 个过期备份。")
        for d in deleted:
            print(f"  - {d}")


if __name__ == "__main__":
    main()
