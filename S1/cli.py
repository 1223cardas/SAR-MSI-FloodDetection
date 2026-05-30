from Aquisition.aquireProducts import aquireProducts, aquireProductsFromLog
from mainconfig import input
PRODUCT_COLLECTION = "sentinel-1-grd"


def terminal():
	while True:
		print("\nMenu:")
		print("1. Run product discovery")
		print("2. Run from search log")
		print("3. Exit")

		choice = input("Choose an option: ", expected_type=str)
		try:
			if choice == "1":
				aquireProducts(PRODUCT_COLLECTION)
				
			elif choice == "2":
				aquireProductsFromLog()
			elif choice == "3":
				print("Exiting.")
				break
			else:
				print("Invalid choice. Please try again.")
		except Exception as e:
			print(f"An error occurred: {e}. Please try again.")
			

def main():
	terminal()

if __name__ == "__main__":
	main()