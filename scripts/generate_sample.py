import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app
from app.services.relp_sn import AP_FACILITIES_PAYLOAD, gerar_relp_sn


def main():
    app = create_app()
    with app.app_context():
        exportacao = gerar_relp_sn(AP_FACILITIES_PAYLOAD)
        print(exportacao.as_dict())


if __name__ == "__main__":
    main()
